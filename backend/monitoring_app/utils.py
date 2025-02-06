import re
import json
import math
import pytz
import logging
import datetime
import numpy as np
import pandas as pd
from functools import wraps
from openpyxl import Workbook
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from django.core.cache import cache
from django.http import HttpRequest
from sklearn.neighbors import KDTree
from cryptography.fernet import Fernet
from django.core.mail import send_mail
from django.db.models import Func, Count
from django.utils.html import format_html
from typing import Any, Dict, List, Optional
from rest_framework.response import Response
from collections import defaultdict, Counter
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Alignment, Font, PatternFill

from monitoring_app import models

DAYS = settings.DAYS

logger = logging.getLogger("django")

arcface_model = None

AREA_ADDRESS_MAPPING = {
    "Абылайхана турникет": "Проспект Абылай хана, 51/53",
    "вход в 8 этаж": "Проспект Абылай хана, 51/53",
    "вход Абылайхана": "Проспект Абылай хана, 51/53",
    "военные 3 этаж": "Проспект Абылай хана, 51/53",
    "лифтовые с 1 по 7": "Проспект Абылай хана, 51/53",
    "выход ЦОС": "Проспект Абылай хана, 51/53",
    "Торекулва турникет": "Улица Торекулова, 71",
    "карасай батыра турникет": "Улица Карасай батыра, 75",
}


def get_client_ip(request):
    """Get the client IP address from the request, considering proxy setups."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def format_duration(duration_seconds):
    """Converts a duration in seconds to a more human-readable format."""
    if duration_seconds < 60:
        return f"{duration_seconds:.2f} seconds"
    elif duration_seconds < 3600:
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        return f"{minutes:.0f} minute(s) {seconds:.2f} seconds"
    else:
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        seconds = duration_seconds % 60
        return f"{hours:.0f} hour(s) {minutes:.0f} minute(s) {seconds:.2f} seconds"


class HierarchicalDepartmentFilter(SimpleListFilter):
    title = _("Department")
    parameter_name = "staff_department"

    def lookups(self, request, model_admin):
        departments = models.ChildDepartment.objects.all().select_related("parent")
        return [(dept.id, dept.name) for dept in departments]

    def queryset(self, request, queryset):
        if self.value():
            try:
                department = models.ChildDepartment.objects.get(pk=self.value())
            except models.ChildDepartment.DoesNotExist:
                return queryset

            descendant_ids = self.get_all_descendant_ids(department)
            return queryset.filter(staff__department__in=descendant_ids)
        return queryset

    def get_all_descendant_ids(self, department):
        descendant_ids = set([department.id])
        queue = [department.id]

        while queue:
            current_id = queue.pop(0)
            children = models.ChildDepartment.objects.filter(
                parent_id=current_id
            ).values_list("id", flat=True)
            queue.extend(children)
            descendant_ids.update(children)

        return descendant_ids


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
        bool: True, если пароль соответствует всем требованиям сложности, в противном случае — False
    """
    return bool(
        re.match(
            r"^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$", password
        )
    )


def fetch_data(url: str) -> Dict[str, Any]:
    import requests

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching data: {e}")
        return {}


def parse_attendance_data(data: List[Dict[str, Any]]) -> List[List[Optional[str]]]:
    """
    Parses raw attendance data and returns structured rows for the DataFrame.

    Args:
        data: Raw attendance data from the API or source.

    Returns:
        A list of rows with structured attendance data.
    """
    rows = []
    holidays_cache = cache.get("holidays_cache")

    if not holidays_cache:
        holidays_cache = {
            holiday.date: holiday for holiday in models.PublicHoliday.objects.all()
        }
        cache.set("holidays_cache", holidays_cache, timeout=12 * 60 * 60)

    def parse_datetime_with_timezone(dt_str: Optional[str]) -> Optional[str]:
        if not dt_str:
            return None
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return None

    for record in data:
        for date, details in record.items():
            try:
                date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                date_str = date_obj.strftime("%d.%m.%Y")
            except ValueError:
                continue

            public_holiday = holidays_cache.get(date_obj)
            is_holiday = public_holiday and not public_holiday.is_working_day
            is_weekend = date_obj.weekday() >= 5

            department = details.get("department", "").replace("_", " ").capitalize()
            for attendance in details.get("attendance", []):
                staff_fio = attendance.get("staff_fio", "")
                first_in = parse_datetime_with_timezone(attendance.get("first_in"))
                last_out = parse_datetime_with_timezone(attendance.get("last_out"))
                remote_work = attendance.get("remote_work", False)
                absence_reason = attendance.get("absence_reason", None)
                area_name = attendance.get("area_name", "Unknown Area")

                if is_weekend or is_holiday:
                    if first_in and last_out:
                        attendance_info = f"{first_in} - {last_out}\r\n({area_name})"
                        meta = "holiday_with_attendance"
                    else:
                        attendance_info = "Выходной"
                        meta = "holiday"
                else:
                    if first_in and last_out and absence_reason:
                        attendance_info = f"{first_in} - {last_out}\r\n({area_name})"
                        meta = "workday_with_reason"
                    elif first_in and last_out:
                        attendance_info = f"{first_in} - {last_out}\r\n({area_name})"
                        meta = "workday"
                    elif absence_reason:
                        attendance_info = absence_reason
                        meta = "absence_reason"
                    elif remote_work:
                        attendance_info = "Удаленная работа"
                        meta = "remote_work"
                    else:
                        attendance_info = "Отсутствие"
                        meta = "absence"

                rows.append([staff_fio, department, date_str, attendance_info, meta])
    return rows


def create_dataframe(rows: List[List[Optional[str]]]) -> pd.DataFrame:
    """
    Converts structured rows into a pivoted DataFrame.

    Args:
        rows: List of structured rows containing attendance data.

    Returns:
        A pivoted pandas DataFrame for further processing.
    """
    display_rows = [row[:-1] for row in rows]

    df = pd.DataFrame(display_rows, columns=["ФИО", "Отдел", "Дата", "Посещаемость"])
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


def save_to_excel(
    df_pivot_sorted: pd.DataFrame, rows: List[List[Optional[str]]]
) -> Workbook:
    """
    Форматирует данные посещаемости в Excel-таблицу.

    Args:
        df_pivot_sorted: Поворотный DataFrame с данными посещаемости.
        rows: Оригинальные строки с метаданными для форматирования.

    Returns:
        Объект Workbook из openpyxl.
    """
    wb = Workbook()
    ws = wb.active

    data_font = Font(name="Roboto", size=12)
    header_font = Font(name="Roboto", size=15, bold=True)
    data_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    header_alignment = Alignment(
        horizontal="center", vertical="center", wrap_text=False
    )

    absence_fill = PatternFill(
        start_color="ab0a0a", end_color="ab0a0a", fill_type="solid"
    )
    remote_work_fill = PatternFill(
        start_color="ADD8E6", end_color="ADD8E6", fill_type="solid"
    )
    reason_fill = PatternFill(
        start_color="FFA500", end_color="FFA500", fill_type="solid"
    )
    holiday_fill = PatternFill(
        start_color="D3F9D8", end_color="D3F9D8", fill_type="solid"
    )

    df_flat = df_pivot_sorted.reset_index()
    df_flat_sorted = df_flat.sort_values(by=["Отдел", "ФИО"])

    meta_dict = {(row[0], row[2]): row[-1] for row in rows}

    max_col_widths = [0] * len(df_flat_sorted.columns)
    max_row_heights = [0] * (len(df_flat_sorted) + 1)

    for r_idx, r in enumerate(
        dataframe_to_rows(df_flat_sorted, index=False, header=True), 1
    ):
        for c_idx, value in enumerate(r, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)

            if r_idx == 1:
                cell.font = header_font
                cell.alignment = header_alignment
            else:
                cell.font = data_font
                cell.alignment = data_alignment

                if c_idx > 2:
                    staff_fio = r[0]
                    date = df_flat_sorted.columns[c_idx - 1]
                    meta = meta_dict.get((staff_fio, date), None)
                    if meta == "holiday_with_attendance":
                        cell.fill = holiday_fill
                    elif meta == "absence_reason":
                        cell.fill = reason_fill
                    elif meta == "remote_work":
                        cell.fill = remote_work_fill
                    elif meta == "absence":
                        cell.fill = absence_fill
                        cell.font = Font(color="FFFFFF")

            value_length = len(str(value)) if value else 0
            max_col_widths[c_idx - 1] = max(max_col_widths[c_idx - 1], value_length + 2)
            max_row_heights[r_idx - 1] = max(max_row_heights[r_idx - 1], value_length)

    for idx, col_width in enumerate(max_col_widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = max(
            col_width, 15
        )

    for idx, row_height in enumerate(max_row_heights, start=1):
        ws.row_dimensions[idx].height = max(row_height * 2, 25)

    return wb


def add_api_key_header(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request = args[0]

        if isinstance(request, HttpRequest):
            api_key = models.APIKey.objects.filter(is_active=True).first()
            if api_key:
                request.META["HTTP_X_API_KEY"] = api_key.key
            else:
                return Response(
                    {"error": "No active API key available for authentication."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        return func(*args, **kwargs)

    return wrapper


def send_password_reset_email(user, request):
    reset_link = f"{request.scheme}://{request.get_host()}{reverse('password_reset_confirm', args=[models.PasswordResetToken.generate_token(user)])}"

    subject = "Инструкция по сбросу пароля"
    html_message = format_html(
        """
        <div style="font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ececec; border-radius: 10px; background-color: #ffffff;">
            <h2 style="color: #007bff; text-align: center; margin-bottom: 20px;">Сброс пароля</h2>
            <p style="color: #333; line-height: 1.6; margin-bottom: 20px; text-align: center;">
                Здравствуйте, {username}. Вы запросили сброс пароля для своего аккаунта. 
                Пожалуйста, нажмите кнопку ниже, чтобы сбросить пароль.
            </p>
            <div style="text-align: center; margin-bottom: 30px;">
                <a href="{reset_link}" style="display: inline-block; padding: 15px 30px; color: #ffffff; background-color: #007bff; text-decoration: none; border-radius: 5px; font-size: 18px; font-weight: bold;">
                    Сбросить пароль
                </a>
            </div>
            <p style="color: #555; line-height: 1.6; margin-bottom: 20px; text-align: center;">
                Ссылка для сброса пароля действительна в течение <strong>1 часа</strong>. Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.
            </p>
            <hr style="border: none; border-top: 1px solid #ececec; margin: 30px 0;">
            <p style="font-size: 12px; color: #999; text-align: center;">
                Мы рады помочь вам сохранить безопасность вашего аккаунта. 
            </p>
        </div>
        """,
        username=user.username,
        reset_link=reset_link,
    )

    plain_message = (
        f"Здравствуйте, {user.username}!\n\n"
        "Вы получили это письмо, потому что был запрошен сброс пароля для вашего аккаунта.\n\n"
        f"Для сброса пароля перейдите по следующей ссылке: {reset_link}\n\n"
        "Эта ссылка будет действительна в течение 1 часа. Для вашей безопасности не передавайте эту ссылку другим лицам.\n\n"
        "Если вы не запрашивали сброс пароля, проигнорируйте это письмо, и ваш пароль останется неизменным.\n\n"
        "С уважением,\n"
        "Команда поддержки."
    )

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
    )


def get_user_timezone(request):
    user_timezone = request.session.get("timezone")
    if not user_timezone:
        user_timezone = settings.TIME_ZONE
    return pytz.timezone(user_timezone)


def normalize_id(department_id):
    """
    Нормализует ID отдела, удаляя ведущие нули, если ID состоит только из цифр.
    Если ID содержит буквы, он остаётся без изменений.

    Args:
        department_id (str): ID отдела.

    Returns:
        str: Нормализованный ID.
    """
    if department_id.isdigit():
        return str(int(department_id))
    return department_id


def transliterate(name):
    slovar = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        " ": " ",
        "-": "-",
        ".": ".",
        ",": ",",
        "!": "!",
        "?": "?",
        ":": ":",
    }

    name = name.lower()
    translit = []
    for letter in name:
        translit.append(slovar.get(letter, letter))

    return "".join(translit)


class Radians(Func):
    function = "RADIANS"


class Cos(Func):
    function = "COS"


def clean_address(address):
    """
    Очищает адрес, удаляя префиксы ('Улица', 'Проспект', и т.д.),
    скрытые символы и нормализует пробелы.

    Args:
        address (str): Исходный адрес.

    Returns:
        str: Очищенный и нормализованный адрес.
    """
    if address:
        address = address.replace("\u200b", "")
        address = re.sub(
            r"^(улица|проспект|переулок|бульвар|территория|микрорайон)\s+",
            "",
            address,
            flags=re.IGNORECASE,
        )
        address = re.sub(r"\s+", " ", address).strip().lower()
        return address
    return address


def generate_map_data(
    locations, date_at, search_staff_attendance=True, filter_empty=False
):
    """
    Генерирует данные по локациям, включая посещения сотрудников и занятия.

    Args:
        locations (QuerySet): Локации из модели ClassLocation.
        date_at (date): Дата для фильтрации данных (дата события).
        search_staff_attendance (bool): Если True, включает данные из StaffAttendance и LessonAttendance.
        filter_empty (bool): Если True, исключает локации с нулевым количеством посещений.

    Returns:
        list: Список словарей с данными по локациям, готовых для отображения на карте.
    """
    staff_by_address = defaultdict(int)
    lesson_attendance_by_address = defaultdict(int)

    if search_staff_attendance:
        try:
            data_insert_date = date_at + datetime.timedelta(days=1)
            logger.info(
                f"Начинаем обработку StaffAttendance для даты вставки: {data_insert_date} (дата события: {date_at})"
            )

            staff_attendances = (
                models.StaffAttendance.objects.filter(
                    date_at=data_insert_date, first_in__isnull=False
                )
                .values("area_name_in")
                .annotate(count=Count("id"))
            )

            if not staff_attendances:
                logger.warning(
                    f"Нет записей StaffAttendance для даты вставки {data_insert_date}"
                )
            else:
                for attendance in staff_attendances:
                    area_name_in = attendance.get("area_name_in")
                    if not area_name_in:
                        logger.warning(
                            f"Найдена запись StaffAttendance без area_name_in для даты вставки {data_insert_date}"
                        )
                        continue
                    address = AREA_ADDRESS_MAPPING.get(area_name_in)
                    if address:
                        comparison_address = clean_address(address)
                        matched_location = next(
                            (
                                loc
                                for loc in locations
                                if clean_address(loc.address) == comparison_address
                            ),
                            None,
                        )
                        if matched_location:
                            original_address = matched_location.address.strip()
                            staff_by_address[original_address] += attendance.get(
                                "count", 0
                            )
                        else:
                            logger.warning(
                                f"Оригинальный адрес для '{area_name_in}' не найден в ClassLocation"
                            )
                    else:
                        logger.warning(
                            f"Название зоны '{area_name_in}' не найдено в AREA_ADDRESS_MAPPING"
                        )

                logger.info(f"Обработано StaffAttendance: {dict(staff_by_address)}")

            staff_with_attendance_qs = models.StaffAttendance.objects.filter(
                date_at=data_insert_date, first_in__isnull=False
            ).values_list("staff_id", flat=True)
            staff_with_attendance = list(staff_with_attendance_qs)
            staff_count = len(staff_with_attendance)
            logger.info(f"Количество сотрудников с посещением: {staff_count}")

            logger.info(f"Начинаем обработку LessonAttendance для даты: {date_at}")

            lesson_attendances_qs = models.LessonAttendance.objects.filter(
                date_at=date_at
            ).exclude(staff_id__in=staff_with_attendance)

            lesson_count = lesson_attendances_qs.count()
            logger.info(f"Количество LessonAttendance для обработки: {lesson_count}")

            if lesson_count > 0:
                lesson_coords = list(
                    lesson_attendances_qs.values_list("latitude", "longitude")
                )

                class_locations = list(models.ClassLocation.objects.all())
                if not class_locations:
                    logger.warning("Нет записей ClassLocation.")
                    return []

                class_coords = [
                    (loc.latitude, loc.longitude) for loc in class_locations
                ]
                class_addresses = [loc.address.strip() for loc in class_locations]

                kd_tree = KDTree(class_coords, metric="euclidean")
                logger.info("KDTree успешно построен.")

                distances, indices = kd_tree.query(lesson_coords, k=1)
                logger.info("KDTree запрос завершен.")

                if hasattr(indices, "ndim") and indices.ndim > 1:
                    indices = indices.flatten()
                else:
                    indices = indices

                try:
                    nearest_addresses = [class_addresses[int(idx)] for idx in indices]
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"Ошибка при преобразовании индексов KDTree: {e}", exc_info=True
                    )
                    raise

                address_counts = Counter(nearest_addresses)
                lesson_attendance_by_address = defaultdict(int, address_counts)

                logger.info(
                    f"Обработано LessonAttendance: {dict(lesson_attendance_by_address)}"
                )
            else:
                logger.info("Нет записей LessonAttendance для обработки.")
        except Exception as e:
            logger.error(
                f"Ошибка при обработке данных посещений: {str(e)}", exc_info=True
            )
            raise

    try:
        aggregated_data = defaultdict(int)
        for address, count in staff_by_address.items():
            aggregated_data[address] += count
        for address, count in lesson_attendance_by_address.items():
            aggregated_data[address] += count
        logger.info(f"Агрегированные данные: {dict(aggregated_data)}")
    except Exception as e:
        logger.error(f"Ошибка при агрегации данных: {str(e)}", exc_info=True)
        raise

    result_list = []
    try:
        for loc in locations:
            original_address = loc.address.strip()
            location_data = {
                "name": loc.name,
                "address": original_address,
                "lat": loc.latitude,
                "lng": loc.longitude,
            }
            if search_staff_attendance:
                employees_count = aggregated_data.get(original_address, 0)
                if employees_count > 0:
                    location_data["employees"] = employees_count
                    if filter_empty and employees_count <= 1:
                        continue
                else:
                    continue
            result_list.append(location_data)
        logger.info(f"Сформирован список результатов с {len(result_list)} локациями.")
    except Exception as e:
        logger.error(
            f"Ошибка при формировании списка результатов: {str(e)}", exc_info=True
        )
        raise

    try:
        main_location = next(
            (
                item
                for item in result_list
                if re.search(
                    r"абылай\s*хана",
                    re.sub(r"[\"\'.,]", "", item["address"].lower()).strip(),
                )
            ),
            None,
        )

        if main_location:
            result_list.remove(main_location)
            result_list.insert(0, main_location)
            logger.info("Основная локация перемещена в начало списка.")
        else:
            result_list.sort(key=lambda x: x["name"])
            logger.info("Основная локация не найдена. Список отсортирован по имени.")
    except Exception as e:
        logger.error(
            f"Ошибка при сортировке списка результатов: {str(e)}", exc_info=True
        )

    return result_list


class LocationSearcher:
    def __init__(self, locations):
        """
        Инициализация с использованием списка локаций.

        Args:
            locations (list): Список словарей с ключами `latitude`, `longitude`, `name`.
        """
        self.locations = locations
        self.kd_tree = KDTree(
            np.array([(loc["latitude"], loc["longitude"]) for loc in locations]),
            metric="euclidean",
        )
        self.names = [loc["name"] for loc in locations]

    def find_nearest(self, lat, lon, radius=200):
        """
        Находит ближайшую локацию в заданном радиусе.

        Args:
            lat (float): Широта искомой точки.
            lon (float): Долгота искомой точки.
            radius (float): Радиус поиска в метрах.

        Returns:
            str: Название ближайшей локации или "Unknown Area".
        """
        meters_to_degrees = radius / 111000
        indices = self.kd_tree.query_radius([[lat, lon]], r=meters_to_degrees)[0]
        if len(indices) > 0:
            return self.names[indices[0]]
        return "Unknown Area"


def is_within_radius(lat1, lon1, lat2, lon2, radius=200):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance <= radius


def extract_coordinates(geo_data):
    """
    Extracts latitude and longitude from a geo data string formatted as 'longitude%2Clatitude'.

    This function searches the input string `geo_data` for a latitude-longitude pair in the
    format `longitude%2Clatitude` (e.g., "76.929225%2C43.254926"). The latitude and longitude
    values are extracted, converted to floats, and returned in the order (latitude, longitude).

    Args:
        geo_data (str): A string containing latitude and longitude data in the
            format 'longitude%2Clatitude'.

    Returns:
        tuple: A tuple (latitude, longitude) if the coordinates are successfully extracted,
        or (None, None) if the input string is invalid or does not contain recognizable coordinates.

    Example:
        >>> extract_coordinates("76.929225%2C43.254926")
        (43.254926, 76.929225)
    """
    match = re.search(r"(\d{2}\.\d+)%2C(\d{2}\.\d+)", geo_data)
    if match:
        return match.group(2), match.group(1)
    return (None, None)


def get_bonus_percentage(num_days, percent_for_period):
    """
    Определяет бонус на основе количества рабочих дней и итогового процента посещаемости.

    Если итоговый процент больше 100, по-прежнему осуществляется поиск правила.
    Если подходящего правила не найдено, возвращается 0.

    Аргументы:
        num_days (int): Количество уникальных рабочих дней в периоде.
        percent_for_period (float): Итоговый процент присутствия за период.

    Возвращает:
        float: Вычисленный бонус в процентах.
    """
    rule = models.PerformanceBonusRule.objects.filter(
        min_days__lte=num_days,
        max_days__gte=num_days,
        min_attendance_percent__lte=percent_for_period,
        max_attendance_percent__gte=percent_for_period,
    ).first()

    if rule:
        return float(rule.bonus_percentage)

    return 0.0
