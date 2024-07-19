import re
import json
import datetime
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
from openpyxl import Workbook
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from monitoring_app import models
from django.core.cache import cache
from cryptography.fernet import Fernet
from openpyxl.styles import Alignment, Font
from openpyxl.utils.dataframe import dataframe_to_rows

DAYS = settings.DAYS


class APIKeyUtility:
    _secret_key = None

    @staticmethod
    def get_secret_key():
        if APIKeyUtility._secret_key is None:
            if not settings.SECRET_API:
                secret_key = Fernet.generate_key().decode("utf-8")

                dotenv = settings.DOTENV_PATH

                with open(dotenv, mode="ab") as f:
                    f.write(f"""\nSECRET_API={secret_key}\n""".encode("utf-8"))

                APIKeyUtility._secret_key = secret_key
            else:
                APIKeyUtility._secret_key = settings.SECRET_API

        return APIKeyUtility._secret_key

    @staticmethod
    def encrypt_data(data, secret_key):
        f = Fernet(secret_key.encode())
        encrypted_data = f.encrypt(json.dumps(data).encode())
        return encrypted_data.decode()

    @staticmethod
    def decrypt_data(encrypted_data, secret_key, fields=("is_active",)):
        f = Fernet(secret_key.encode())
        decrypted_data = f.decrypt(encrypted_data.encode())
        data = json.loads(decrypted_data.decode())

        return {field: data.get(field) for field in fields}

    @staticmethod
    def generate_api_key(key_name, created_by):
        secret_key = APIKeyUtility.get_secret_key()
        data = {
            "key_name": key_name,
            "created_by": created_by.username,
            "created_at": timezone.now().isoformat(),
            "is_activate": True,
        }
        encrypted_data = APIKeyUtility.encrypt_data(data, secret_key)
        return encrypted_data, secret_key


def get_attendance_data(pin: str):
    """
    Получает данные о посещаемости сотрудника за предыдущий день.

    Args:
        pin (str): Идентификационный номер сотрудника (PIN-код).

    Returns:
        list: Список словарей, содержащих информацию о каждом проходе
              сотрудника через систему контроля доступа за указанный день.
              Если произошла ошибка, возвращает пустой список.
    """
    prev_date = datetime.datetime.now() - datetime.timedelta(days=DAYS)

    eventTime_first = prev_date.strftime("%Y-%m-%d 00:00:00")
    eventTime_last = prev_date.strftime("%Y-%m-%d 23:59:59")
    access_token = settings.API_KEY

    try:
        params = {
            "endDate": eventTime_last,
            "pageNo": "1",
            "pageSize": "1000",
            "personPin": pin,
            "startDate": eventTime_first,
            "access_token": access_token,
        }
        response = requests.get(
            settings.API_URL + "/api/transaction/listAttTransaction",
            params=params,
        )
        response.raise_for_status()
        response_json = response.json()
        return response_json.get("data", [])
    except Exception as e:
        print(f"Error, Pin: {pin}, Error: {e}")
        return []


def get_all_attendance():
    """
    Получает данные о посещаемости всех сотрудников за текущий день
    и сохраняет их в базе данных.

    Выполняет запрос данных о посещаемости для каждого сотрудника
    параллельно с помощью ThreadPoolExecutor. Затем для каждого
    сотрудника извлекает первое и последнее время прохода
    (если данные о посещаемости имеются) и сохраняет их
    в модели StaffAttendance.

    Returns:
        None
    """
    pins = models.Staff.objects.values_list("pin", flat=True)
    attendance_data = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        for pin, data in zip(pins, executor.map(get_attendance_data, pins)):
            attendance_data[pin] = data

    prev_date = timezone.now() - timezone.timedelta(days=DAYS)
    next_day = prev_date + timezone.timedelta(days=0)

    updates = []

    for pin, data in attendance_data.items():
        staff = models.Staff.objects.get(pin=pin)
        if data:
            first_event_time = timezone.make_aware(
                timezone.datetime.fromisoformat(data[-1]["eventTime"])
            )
            last_event_time = (
                timezone.make_aware(
                    timezone.datetime.fromisoformat(data[0]["eventTime"])
                )
                if len(data) > 1
                else first_event_time
            )
        else:
            first_event_time = None
            last_event_time = None

        date_at = next_day.date() + timezone.timedelta(days=1)

        attendance, created = models.StaffAttendance.objects.get_or_create(
            staff=staff,
            date_at=date_at,
            defaults={"first_in": first_event_time, "last_out": last_event_time},
        )
        if not created:
            attendance.first_in = first_event_time
            attendance.last_out = last_event_time
            updates.append(attendance)

    with transaction.atomic():
        if updates:
            models.StaffAttendance.objects.bulk_update(
                updates, ["first_in", "last_out"]
            )


def password_check(password: str) -> bool:
    """
    Проверяет, соответствует ли пароль требованиям сложности системы.

    Эта функция проверяет строку пароля на основе следующих критериев:

        - Минимальная длина 8 символов.
        - Содержит хотя бы одну заглавную букву (A-Z)
        - Содержит хотя бы одну строчную букву (a-z)
        - Содержит хотя бы одну цифру (0-9)
        - Содержит хотя бы один специальный символ из следующего набора: #?!@$%^&*-

    Args:
        пароль (str): строка пароля, которую необходимо проверить.

    Returns:
        bool: True, если пароль соответствует всем требованиям сложности, в противном случае — False.
    """
    return bool(
        re.match(
            r"^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$", password
        )
    )


def fetch_data(url: str) -> Dict[str, Any]:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return {}


def parse_attendance_data(data: List[Dict[str, Any]]) -> List[List[Optional[str]]]:
    rows: List[List[Optional[str]]] = []
    timezone_pattern = re.compile(r"\+\d{2}:\d{2}")
    holidays_cache = cache.get("holidays_cache")

    if not holidays_cache:
        holidays_cache = {
            holiday.date: holiday for holiday in models.PublicHoliday.objects.all()
        }
        cache.set("holidays_cache", holidays_cache, timeout=60 * 60 * 24)

    def parse_datetime_with_timezone(dt_str: Optional[str]) -> Optional[str]:
        if not dt_str:
            return None
        match = timezone_pattern.search(dt_str)
        if match:
            timezone = match.group(0)
            dt_format = f"%Y-%m-%dT%H:%M:%S{timezone}"
            return datetime.datetime.strptime(dt_str, dt_format).strftime("%H:%M:%S")
        return None

    for record in data:
        for date, details in record.items():
            try:
                date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
                date_str = date_obj.strftime("%d.%m.%Y")
            except ValueError as e:
                print(f"Error parsing date: {e}")
                continue

            public_holiday = holidays_cache.get(date_obj)
            is_holiday = public_holiday and not public_holiday.is_working_day

            department = details.get("department", "").replace("_", " ").capitalize()
            for attendance in details.get("attendance", []):
                try:
                    staff_fio = attendance.get("staff_fio", "")
                    first_in = parse_datetime_with_timezone(attendance.get("first_in"))
                    last_out = parse_datetime_with_timezone(attendance.get("last_out"))

                    if date_obj.weekday() >= 5 or is_holiday:
                        if first_in and last_out:
                            attendance_info = f"{first_in} - {last_out}"
                        else:
                            attendance_info = "Выходной"
                    else:
                        attendance_info = (
                            f"{first_in} - {last_out}"
                            if first_in and last_out
                            else "Отсутствие"
                        )

                    rows.append([staff_fio, department, date_str, attendance_info])
                except KeyError as e:
                    print(f"Missing expected key: {e}")
                except Exception as e:
                    print(f"Error processing record: {e}")
    return rows


def create_dataframe(rows: List[List[Optional[str]]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ФИО", "Отдел", "Дата", "Посещаемость"])
    df_pivot = df.pivot_table(
        index=["ФИО", "Отдел"],
        columns="Дата",
        values="Посещаемость",
        aggfunc="first",
        fill_value="Отсутствие",
    )
    df_pivot_sorted = df_pivot.reindex(
        sorted(
            df_pivot.columns,
            key=lambda x: pd.to_datetime(x, format="%d.%m.%Y"),
            reverse=True,
        ),
        axis=1,
    )
    return df_pivot_sorted


def save_to_excel(df_pivot_sorted: pd.DataFrame) -> Workbook:
    wb = Workbook()
    ws = wb.active

    data_font = Font(name="Roboto", size=11)
    data_alignment = Alignment(horizontal="center", vertical="center")

    df_flat = df_pivot_sorted.reset_index()
    df_flat_sorted = df_flat.sort_values(by=["Отдел", "ФИО"])

    for r_idx, r in enumerate(
        dataframe_to_rows(df_flat_sorted, index=False, header=True), 1
    ):
        for c_idx, value in enumerate(r, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.font = data_font
            cell.alignment = data_alignment

    header_font = Font(name="Roboto", size=14, bold=True)
    for cell in ws[1]:
        cell.font = header_font

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except TypeError:
                pass
        adjusted_width = max_length + 2
        ws.column_dimensions[column].width = adjusted_width

    for row in ws.iter_rows():
        max_height = 0
        for cell in row:
            try:
                if len(str(cell.value)) > max_height:
                    max_height = len(cell.value)
            except TypeError:
                pass
        adjusted_height = max_height * 3
        ws.row_dimensions[row[0].row].height = adjusted_height

    return wb
