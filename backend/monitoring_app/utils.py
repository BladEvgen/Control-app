import re
import json
import math
import pytz
import logging
import datetime
import numpy as np
import pandas as pd
from typing import Any, Dict
from openpyxl import Workbook
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from monitoring_app import models
from sklearn.neighbors import KDTree
from cryptography.fernet import Fernet
from django.core.mail import send_mail
from django.db.models import Func, Count
from django.utils.html import format_html
from collections import defaultdict, Counter
from monitoring_app.cache_conf import get_cache
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from openpyxl.styles import Alignment, Font, PatternFill

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


def send_password_reset_email(user, request):
    """
    Send a password reset email to the user with branding and design consistent with the website footer.

    Args:
        user: The user object who requested password reset
        request: The request object to build the reset URL

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        token = models.PasswordResetToken.generate_token(user)

        site_name = getattr(settings, "SITE_NAME", "KRMU")

        reset_scheme = "https" if request.is_secure() else request.scheme
        reset_link = f"{reset_scheme}://{request.get_host()}{reverse('password_reset_confirm', args=[token])}"

        expiry_time = timezone.now() + datetime.timedelta(hours=1)
        expiry_time_str = expiry_time.strftime("%H:%M %d.%m.%Y")

        current_year = timezone.now().year

        user_display_name = getattr(user, "first_name", user.username) or user.username

        subject = f"Сброс пароля на сайте {site_name}"

        html_message = format_html(
            """
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Сброс пароля</title>
            </head>
            <body style="margin: 0; padding: 0; font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', sans-serif; background-color: #f7f9fc; color: #333333;">
                <div style="max-width: 600px; margin: 20px auto; padding: 30px; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #2563EB; font-size: 24px; margin: 0 0 5px 0;">Сброс пароля</h1>
                        <p style="color: #6B7280; font-size: 16px; margin: 0;">Инструкция по восстановлению доступа</p>
                    </div>
                    
                    <div style="padding: 20px; background-color: #F3F4F6; border-radius: 8px; margin-bottom: 25px;">
                        <p style="color: #4B5563; line-height: 1.6; margin: 0 0 15px 0;">
                            Здравствуйте, <strong>{user_name}</strong>!
                        </p>
                        <p style="color: #4B5563; line-height: 1.6; margin: 0 0 15px 0;">
                            Мы получили запрос на сброс пароля для вашего аккаунта. Если это были вы, используйте кнопку ниже для создания нового пароля.
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin-bottom: 30px;">
                        <a href="{reset_link}" style="display: inline-block; padding: 14px 32px; color: #ffffff; background-color: #2563EB; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; transition: background-color 0.2s ease;">
                            Сбросить пароль
                        </a>
                    </div>
                    
                    <div style="border-left: 4px solid #FCD34D; padding: 12px 15px; background-color: #FFFBEB; margin-bottom: 25px; border-radius: 0 6px 6px 0;">
                        <p style="color: #92400E; font-size: 14px; line-height: 1.5; margin: 0;">
                            <strong>Важно:</strong> Ссылка действительна до <strong>{expiry_time}</strong>.<br>
                            Если вы не запрашивали сброс пароля, пожалуйста, игнорируйте это письмо или обратитесь в службу поддержки.
                        </p>
                    </div>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #E5E7EB; text-align: center;">
                        <div style="display: inline-block; margin: 0 15px 15px 0;">
                            <a href="{site_url}" style="color: #4B5563; text-decoration: none; font-size: 14px;">
                                Home
                            </a>
                        </div>
                        <div style="display: inline-block; margin: 0 15px 15px 0;">
                            <a href="https://new.krmu.edu.kz" style="color: #4B5563; text-decoration: none; font-size: 14px;">
                                KRMU
                            </a>
                        </div>
                        <div style="display: inline-block; margin: 0 0 15px 0;">
                            <a href="https://new.krmu.edu.kz/О_нас/Об_университете/" style="color: #4B5563; text-decoration: none; font-size: 14px;">
                                About Us
                            </a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """,
            user_name=user_display_name,
            reset_link=reset_link,
            expiry_time=expiry_time_str,
            site_name=site_name,
            current_year=current_year,
            site_url=f"{reset_scheme}://{request.get_host()}/",
        )

        plain_message = (
            f"Сброс пароля на сайте {site_name}\n"
            f"=============================================\n\n"
            f"Здравствуйте, {user_display_name}!\n\n"
            "Мы получили запрос на сброс пароля для вашего аккаунта.\n\n"
            f"Для создания нового пароля перейдите по следующей ссылке:\n{reset_link}\n\n"
            f"Важно: Ссылка действительна до {expiry_time_str}.\n\n"
            "Если вы не запрашивали сброс пароля, пожалуйста, игнорируйте это письмо\n"
            "или обратитесь в службу поддержки.\n\n"
            "---\n"
            "Home: https://krmu.edu.kz\n"
            "KRMU: https://new.krmu.edu.kz\n"
            "About Us: https://new.krmu.edu.kz/О_нас/Об_университете/\n\n"
            f"© {current_year} {site_name}, Inc."
        )

        success = send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        if success:
            logger.info(f"Password reset email sent for user ID: {user.id}")

            if hasattr(models, "SecurityAuditLog"):
                models.SecurityAuditLog.objects.create(
                    user=user,
                    action_type="password_reset_request",
                    ip_address=request.META.get("REMOTE_ADDR", ""),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )

            return True
        else:
            logger.error(f"Failed to send password reset email to user ID: {user.id}")
            return False

    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}")
        return False


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


def get_all_child_departments(department):
    """
    Recursively get all child departments of a given department.

    Args:
        department: The parent department

    Returns:
        List of departments including the parent and all children
    """
    result = [department]
    children = models.ChildDepartment.objects.filter(parent=department)

    for child in children:
        result.extend(get_all_child_departments(child))

    return result


def collect_attendance_data(staff_list, start_date, end_date):
    """
    Collect attendance data for staff within the date range.
    Data is cached for 6 hours.

    Args:
        staff_list: QuerySet of Staff objects
        start_date: Start date for attendance data
        end_date: End date for attendance data

    Returns:
        List of attendance data organized by date and staff
    """

    def generate_cache_key():
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        dept_ids = sorted(
            set(staff.department_id for staff in staff_list if staff.department_id is not None)
        )
        dept_str = f"dept_{'_'.join(map(str, dept_ids))}" if dept_ids else "no_dept"

        staff_ids = sorted(staff_list.values_list("id", flat=True))
        staff_count = len(staff_ids)

        return f"attendance_data_{start_str}_to_{end_str}_{dept_str}_staff_count_{staff_count}"

    cache_key = generate_cache_key()
    cached_results = get_cache(
        cache_key,
        query=lambda: _collect_attendance_data_impl(staff_list, start_date, end_date),
        timeout=6 * 60 * 60,
    )

    return cached_results


def _collect_attendance_data_impl(staff_list, start_date, end_date):
    """
    Implementation of attendance data collection.
    """
    from django.db.models import Q

    logger.info(
        f"Collecting attendance data from {start_date} to {end_date} for {staff_list.count()} staff members"
    )

    date_range = [
        start_date + datetime.timedelta(days=i) for i in range((end_date - start_date).days + 1)
    ]

    staff_ids = list(staff_list.values_list("id", flat=True))

    holidays = get_cache(
        "public_holidays",
        query=lambda: {
            holiday.date: holiday.is_working_day
            for holiday in models.PublicHoliday.objects.filter(date__range=[start_date, end_date])
        },
        timeout=10 * 60,  # 10 minutes
    )

    attendance_qs = models.StaffAttendance.objects.filter(
        staff_id__in=staff_ids,
        date_at__range=[
            start_date + datetime.timedelta(days=1),
            end_date + datetime.timedelta(days=1),
        ],
    ).select_related("staff")

    remote_work_qs = models.RemoteWork.objects.filter(
        Q(staff_id__in=staff_ids)
        & (Q(start_date__lte=end_date, end_date__gte=start_date) | Q(permanent_remote=True))
    ).select_related("staff")

    absence_qs = models.AbsentReason.objects.filter(
        staff_id__in=staff_ids, start_date__lte=end_date, end_date__gte=start_date
    ).select_related("staff")

    attendance_map = defaultdict(lambda: defaultdict(dict))
    for att in attendance_qs:
        local_date = (
            convert_to_local(att.first_in)
            if att.first_in
            else convert_to_local(att.date_at) - datetime.timedelta(days=1)
        )
        date_key = local_date.strftime("%Y-%m-%d")
        staff_id = att.staff_id

        first_in_local = convert_to_local(att.first_in) if att.first_in else None
        last_out_local = convert_to_local(att.last_out) if att.last_out else None

        if staff_id not in attendance_map[date_key]:
            attendance_map[date_key][staff_id] = {
                "first_in": first_in_local,
                "last_out": last_out_local,
                "area_name": att.area_name_in,
            }
        else:
            current_rec = attendance_map[date_key][staff_id]
            if att.first_in and (
                not current_rec["first_in"]
                or convert_to_local(att.first_in) < current_rec["first_in"]
            ):
                current_rec["first_in"] = convert_to_local(att.first_in)
            if att.last_out and (
                not current_rec["last_out"]
                or convert_to_local(att.last_out) > current_rec["last_out"]
            ):
                current_rec["last_out"] = convert_to_local(att.last_out)

    remote_work_map = defaultdict(set)
    for rw in remote_work_qs:
        staff_id = rw.staff_id

        rw_start = start_date if rw.permanent_remote else max(rw.start_date, start_date)
        rw_end = end_date if rw.permanent_remote else min(rw.end_date, end_date)

        date_keys = [
            (rw_start + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((rw_end - rw_start).days + 1)
        ]

        for date_key in date_keys:
            remote_work_map[date_key].add(staff_id)

    absence_map = defaultdict(lambda: defaultdict(list))
    for absence in absence_qs:
        staff_id = absence.staff_id
        abs_start = max(absence.start_date, start_date)
        abs_end = min(absence.end_date, end_date)

        for i in range((abs_end - abs_start).days + 1):
            current = abs_start + datetime.timedelta(days=i)
            date_key = current.strftime("%Y-%m-%d")
            absence_map[date_key][staff_id].append(
                {"reason": absence.get_reason_display(), "approved": absence.approved}
            )

    results = []
    staff_data_cache = {
        staff.id: (
            f"{staff.surname} {staff.name}",
            staff.department.name if staff.department else "N/A",
        )
        for staff in staff_list
    }

    for date in date_range:
        date_str = date.strftime("%Y-%m-%d")
        date_display = date.strftime("%d.%m.%Y")
        is_weekend = date.weekday() >= 5
        is_holiday = date in holidays and not holidays[date]
        is_off_day = is_weekend or is_holiday

        for staff in staff_list:
            staff_id = staff.id
            staff_fio, department_name = staff_data_cache[staff_id]

            attendance = None
            if staff_id in attendance_map.get(date_str, {}):
                att_data = attendance_map[date_str][staff_id]
                first_in = att_data["first_in"]
                last_out = att_data["last_out"]

                if first_in and last_out:
                    attendance = (
                        f"{first_in.strftime('%H:%M:%S')} - {last_out.strftime('%H:%M:%S')}\n"
                        f"({att_data['area_name']})"
                    )

            is_remote = staff_id in remote_work_map.get(date_str, set())
            has_absence = staff_id in absence_map.get(date_str, {})

            if is_off_day:
                status_info = attendance if attendance else "Выходной"
                meta = "holiday_with_attendance" if attendance else "holiday"
            else:
                if is_remote:
                    status_info = "Удаленная работа"
                    meta = "remote_work"
                elif has_absence:
                    absence_info = absence_map[date_str][staff_id][0]
                    status_info = absence_info["reason"]
                    meta = (
                        "absence_reason_approved" if absence_info["approved"] else "absence_reason"
                    )
                elif attendance:
                    status_info = attendance
                    meta = "workday"
                else:
                    status_info = "Отсутствие"
                    meta = "absence"

            results.append([staff_fio, department_name, date_display, status_info, meta])

    logger.info(f"Collected {len(results)} attendance records")
    return results


def generate_excel_file(attendance_data, department_name, user_start_date, user_end_date):
    """
    Generate an Excel file from attendance data with improved formatting and filtering.

    Args:
        attendance_data: List of attendance records
            [ФИО, Отдел, 'DD.MM.YYYY', Посещаемость, meta].
            The data has been obtained from the DB and may be for only a subset of the
            user-requested period.
        department_name: Name of the department (str).
        user_start_date: The user-requested start date (datetime.date).
        user_end_date: The user-requested end date (datetime.date).

    Returns:
        Bytes data of the Excel file.
    """
    import io
    from openpyxl.styles import Border, Side
    from openpyxl.utils import get_column_letter

    logger.info("Generating refined Excel file...")

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчет посещаемости"

    title_font = Font(name="Arial", size=16, bold=True)
    subtitle_font = Font(name="Arial", size=12, bold=True)
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Arial", size=10, color="000000")

    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    header_fill = PatternFill(start_color="0070C0", end_color="0070C0", fill_type="solid")
    fill_holiday = PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid")
    fill_holiday_work = PatternFill(start_color="34D399", end_color="34D399", fill_type="solid")
    fill_remote = PatternFill(start_color="38BDF8", end_color="38BDF8", fill_type="solid")
    fill_approved = PatternFill(start_color="A78BFA", end_color="A78BFA", fill_type="solid")
    fill_not_approved = PatternFill(start_color="FB7185", end_color="FB7185", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    ws.merge_cells("A1:E1")
    title_cell = ws.cell(row=1, column=1, value=f"Отчет посещаемости: {department_name}")
    title_cell.font = title_font
    title_cell.alignment = center_wrap

    ws.merge_cells("A2:E2")
    subtitle_cell = ws.cell(
        row=2,
        column=1,
        value=f"Период: {user_start_date.strftime('%d.%m.%Y')} - {user_end_date.strftime('%d.%m.%Y')}",
    )
    subtitle_cell.font = subtitle_font
    subtitle_cell.alignment = center_wrap

    legend_row = 4
    legend_title = ws.cell(row=legend_row, column=1, value="Легенда:")
    legend_title.font = subtitle_font
    legend_title.alignment = center_wrap

    legends = [
        ("Выходной день", fill_holiday),
        ("Работа в выходной", fill_holiday_work),
        ("Удаленная работа", fill_remote),
        ("Одобрено", fill_approved),
        ("Не одобрено", fill_not_approved),
    ]
    for i, (legend_text, legend_fill) in enumerate(legends, start=1):
        row_idx = legend_row + i
        color_cell = ws.cell(row=row_idx, column=1, value="")
        color_cell.fill = legend_fill
        color_cell.border = thin_border
        color_cell.alignment = center_wrap
        desc_cell = ws.cell(row=row_idx, column=2, value=legend_text)
        desc_cell.font = data_font
        desc_cell.border = thin_border
        desc_cell.alignment = center_wrap

    data_start_row = legend_row + len(legends) + 2

    df = pd.DataFrame(attendance_data, columns=["ФИО", "Отдел", "Дата", "Посещаемость", "meta"])
    df["date_obj"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y")
    df = df[
        (df["date_obj"] >= pd.to_datetime(user_start_date))
        & (df["date_obj"] <= pd.to_datetime(user_end_date))
    ]
    if df.empty:
        logger.warning("No attendance data for the selected date range.")

    df = df.sort_values(by="date_obj", ascending=False)

    unique_staff = df[["ФИО", "Отдел"]].drop_duplicates()
    unique_staff = unique_staff.sort_values(by=["Отдел", "ФИО"], ascending=True)

    unique_dates = df["Дата"].unique()

    headers = ["ФИО", "Отдел"] + list(unique_dates)
    for col_idx, header_val in enumerate(headers, start=1):
        cell = ws.cell(row=data_start_row, column=col_idx, value=header_val)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_wrap
        cell.border = thin_border

    attendance_lookup = {}
    meta_lookup = {}
    for row in df.itertuples(index=False):
        key = (row.ФИО, row.Отдел, row.Дата)
        attendance_lookup[key] = row.Посещаемость
        meta_lookup[key] = row.meta

    public_holidays = get_cache(
        "public_holidays_for_excel",
        query=lambda: {
            holiday.date.strftime("%d.%m.%Y"): holiday.is_working_day
            for holiday in models.PublicHoliday.objects.filter(
                date__range=[user_start_date, user_end_date]
            )
        },
        timeout=10 * 60,
    )

    row_idx = data_start_row + 1
    for _, staff_row in unique_staff.iterrows():
        fio = staff_row["ФИО"]
        dept = staff_row["Отдел"]

        fio_cell = ws.cell(row=row_idx, column=1, value=fio)
        fio_cell.font = data_font
        fio_cell.alignment = center_wrap
        fio_cell.border = thin_border

        dept_cell = ws.cell(row=row_idx, column=2, value=dept)
        dept_cell.font = data_font
        dept_cell.alignment = center_wrap
        dept_cell.border = thin_border

        for col_offset, date_str in enumerate(unique_dates, start=3):
            key = (fio, dept, date_str)
            value = attendance_lookup.get(key, "")
            meta = meta_lookup.get(key, "")
            data_cell = ws.cell(row=row_idx, column=col_offset, value=value)
            data_cell.font = data_font
            data_cell.alignment = center_wrap
            data_cell.border = thin_border

            is_working_holiday = date_str in public_holidays and public_holidays[date_str]

            if meta == "holiday":
                if not is_working_holiday:
                    data_cell.fill = fill_holiday
            elif meta == "holiday_with_attendance":
                if not is_working_holiday:
                    data_cell.fill = fill_holiday_work
            elif meta == "remote_work":
                data_cell.fill = fill_remote
            elif meta == "absence_reason_approved":
                data_cell.fill = fill_approved
            elif meta in ["absence", "absence_reason"]:
                data_cell.fill = fill_not_approved
                data_cell.font = Font(name="Arial", size=10, color="FFFFFF")
        row_idx += 1

    for col_idx in range(1, ws.max_column + 1):
        max_length = 0
        col_letter = get_column_letter(col_idx)
        for r_idx in range(1, ws.max_row + 1):
            cell_val = ws.cell(row=r_idx, column=col_idx).value
            if cell_val and isinstance(cell_val, str):
                max_length = max(max_length, len(cell_val))
        ws.column_dimensions[col_letter].width = max_length + 2

    for r_idx in range(1, ws.max_row + 1):
        max_lines = 1
        for c_idx in range(1, ws.max_column + 1):
            cell_val = ws.cell(row=r_idx, column=c_idx).value
            if cell_val and isinstance(cell_val, str):
                max_lines = max(max_lines, cell_val.count("\n") + 1)
        ws.row_dimensions[r_idx].height = 15 * max_lines

    excel_data = io.BytesIO()
    wb.save(excel_data)
    excel_data.seek(0)
    logger.info(
        "Excel file generation completed with proper timezone conversion, filtering, and sorting."
    )
    return excel_data.getvalue()


def convert_to_local(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime.combine(dt, datetime.time(0, 0, 0))
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)
