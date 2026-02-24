import base64
import datetime
import json
import logging
import os
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Generator, List, Tuple, cast

import monitoring_app.tasks as tasks
from celery.result import AsyncResult
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View
from drf_yasg import openapi
from drf_yasg.inspectors import SwaggerAutoSchema
from drf_yasg.utils import merge_params, no_body, swagger_auto_schema
from monitoring_app import (
    async_logic,
    attendance_fetcher,
    ml,
    models,
    permissions,
    serializers,
    utils,
)
from monitoring_app.cache_conf import Cache, get_cache
from monitoring_app.lesson_locations_conf import (
    ACCEPTANCE_R_CLUSTER,
    ACCEPTANCE_R_SAME_POINT,
    ACCEPTANCE_R_STANDALONE,
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
    CLASS_LOCATION_LIST_CACHE_KEY,
    CLASS_LOCATION_LIST_CACHE_TTL,
    CLUSTER_THRESHOLD_M,
    DEFAULT_ACCEPTANCE_RADIUS_M,
    SAME_POINT_THRESHOLD_M,
)
from monitoring_app.signals import invalidate_class_location_cache_impl
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication


def _db_atomic() -> AbstractContextManager[None]:
    """Типизированная обёртка над transaction.atomic() для статического анализа."""
    return cast(AbstractContextManager[None], transaction.atomic())


def _get_manual_parameters_for_inspector(view, method, overrides):
    """manual_parameters из overrides или из _swagger_auto_schema исходной функции (для @api_view)."""
    manual = overrides.get("manual_parameters") or []
    if not manual and method:
        action_method = getattr(view, method.lower(), None)
        if action_method:
            func = getattr(action_method, "__func__", action_method)
            schema = getattr(func, "_swagger_auto_schema", None)
            if isinstance(schema, dict):
                method_data = schema.get(method.lower()) or schema.get(method.upper())
                if isinstance(method_data, dict):
                    manual = method_data.get("manual_parameters") or []
    return manual


class FormOnlySwaggerAutoSchema(SwaggerAutoSchema):
    """Инспектор: при наличии form-параметров в manual_parameters не допускает body (исправляет 500 при генерации схемы)."""

    def add_manual_parameters(self, parameters):
        manual = _get_manual_parameters_for_inspector(
            self.view, self.method, self.overrides
        )
        has_form = any(getattr(p, "in_", None) == openapi.IN_FORM for p in manual)
        if has_form:
            parameters = [
                p for p in parameters if getattr(p, "in_", None) != openapi.IN_BODY
            ]
            return merge_params(parameters, manual)
        return super().add_manual_parameters(parameters)


logger = logging.getLogger(__name__)
lesson_attendance_logger = logging.getLogger("monitoring_app.lesson_attendance")

ExcelRow = Tuple[Any, ...]
User = get_user_model()


@contextmanager
def atomic_block() -> Generator[None, None, None]:
    with transaction.atomic():  # type: ignore[misc]
        yield


LUNCH_BREAK_START = datetime.time(hour=13, minute=0)
LUNCH_BREAK_END = datetime.time(hour=14, minute=0)

CLASS_LOCATION_CACHE_TTL = datetime.timedelta(minutes=60)
CLASS_LOCATION_CACHE = {
    "expires_at": None,
    "kd_tree": None,
    "class_names": [],
    "searcher_payload": [],
    "searcher": None,
}


def get_class_location_cache():
    """
    Кэш локаций: KDTree, LocationSearcher, location_acceptance_radius_m.
    R_loc (60–80 м по умолчанию или acceptance_radius_m из БД) — в Redis и in-memory;
    Celery Beat / warmup_class_location_buffers обновляют.
    """
    now = timezone.now()
    cache_expired = (
        CLASS_LOCATION_CACHE["expires_at"] is None
        or CLASS_LOCATION_CACHE["expires_at"] <= now
    )

    if cache_expired:
        try:
            locations = list(
                models.ClassLocation.objects.only(
                    "id", "name", "latitude", "longitude", "acceptance_radius_m"
                )
            )
            payload = [
                {
                    "name": loc.name,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                }
                for loc in locations
                if loc.latitude is not None and loc.longitude is not None
            ]

            kd_tree = None
            class_names = []
            if payload:
                try:
                    from sklearn.neighbors import KDTree

                    coords = [(item["latitude"], item["longitude"]) for item in payload]
                    kd_tree = KDTree(coords, metric="euclidean")
                    class_names = [item["name"] for item in payload]
                except Exception as exc:
                    logger.warning(f"KDTree initialization failed: {exc}")
                    kd_tree = None
                    class_names = []

            searcher = None
            if payload:
                try:
                    searcher = utils.LocationSearcher(payload)
                except Exception as exc:
                    logger.warning(f"LocationSearcher initialization failed: {exc}")

            locs_with_coords = [
                loc
                for loc in locations
                if loc.latitude is not None and loc.longitude is not None
            ]
            location_acceptance_radius_m = Cache.get(
                CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY
            )
            if location_acceptance_radius_m is None:
                location_acceptance_radius_m = (
                    utils.compute_class_location_acceptance_radii(
                        locs_with_coords,
                        r_same_point=ACCEPTANCE_R_SAME_POINT,
                        r_cluster=ACCEPTANCE_R_CLUSTER,
                        r_standalone=ACCEPTANCE_R_STANDALONE,
                        same_point_threshold=SAME_POINT_THRESHOLD_M,
                        cluster_threshold=CLUSTER_THRESHOLD_M,
                    )
                )
                Cache.set(
                    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
                    location_acceptance_radius_m,
                    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
                )

            CLASS_LOCATION_CACHE.update(
                {
                    "expires_at": now + CLASS_LOCATION_CACHE_TTL,
                    "kd_tree": kd_tree,
                    "class_names": class_names,
                    "searcher_payload": payload,
                    "searcher": searcher,
                    "location_acceptance_radius_m": location_acceptance_radius_m,
                }
            )
        except Exception as exc:
            logger.exception("get_class_location_cache failed: %s", exc)
            CLASS_LOCATION_CACHE["expires_at"] = None
            raise

    return CLASS_LOCATION_CACHE


def calculate_effective_minutes_with_lunch(first_in, last_out):
    """
    Вычисляет количество рабочих минут, исключая обеденный перерыв (13:00-14:00).
    Если интервал перекрывает несколько дней, вычитает обед за каждый день.
    """
    if not first_in or not last_out:
        return 0

    current_tz = timezone.get_current_timezone()
    start = timezone.localtime(first_in, current_tz)
    end = timezone.localtime(last_out, current_tz)

    if end <= start:
        return 0

    total_minutes = (end - start).total_seconds() / 60

    lunch_overlap_minutes = 0
    current_day = start.date()
    while current_day <= end.date():
        lunch_start_dt = timezone.make_aware(
            datetime.datetime.combine(current_day, LUNCH_BREAK_START),
            current_tz,
        )
        lunch_end_dt = timezone.make_aware(
            datetime.datetime.combine(current_day, LUNCH_BREAK_END),
            current_tz,
        )

        overlap_start = max(start, lunch_start_dt)
        overlap_end = min(end, lunch_end_dt)
        if overlap_end > overlap_start:
            lunch_overlap_minutes += (overlap_end - overlap_start).total_seconds() / 60

        current_day += datetime.timedelta(days=1)

    effective_minutes = total_minutes - lunch_overlap_minutes
    return max(effective_minutes, 0)


class StaffAttendancePagination(PageNumberPagination):
    page_size = 5000
    page_size_query_param = "page_size"
    max_page_size = 20000


token_param_config = openapi.Parameter(
    "Authorization",
    in_=openapi.IN_HEADER,
    description="Token [access_token]",
    type=openapi.TYPE_STRING,
)


@permission_classes([AllowAny])
def home(request):
    return render(
        request,
        "index.html",
    )


@permission_classes([AllowAny])
def react_app(request):
    def render_react_app():
        try:
            return render(request, "index.html")
        except Exception as error:
            logger.error(f"React App {str(error)}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        future = executor.submit(render_react_app)
        response = future.result()

    if response is None:
        return HttpResponse(b"Error loading React app", status=500)

    return response


class StaffAttendanceStatsView(APIView):
    """
    Представление для получения статистики о посещаемости персонала.

    Это представление фильтрует данные, чтобы включать только сотрудников, относящихся к отделу с ID AUP.

    Параметры запроса:
        date (str): Дата, для которой запрашивается статистика посещаемости, в формате 'YYYY-MM-DD'. По умолчанию используется текущая дата.
        pin (str): ПИН-код сотрудника для получения конкретной статистики посещаемости.

    Возвращает:
        JSON-ответ, содержащий:
            department_name (str): Название отдела.
            total_staff_count (int): Общее количество сотрудников.
            present_staff_count (int): Количество присутствующих сотрудников.
            absent_staff_count (int): Количество отсутствующих сотрудников.
            present_between_9_to_18 (int): Количество сотрудников, присутствующих с 08:00 до 19:00.
            present_data (list): Список словарей с информацией о присутствующих сотрудниках, включая ПИН, имя, количество минут присутствия и индивидуальный процент.
            absent_data (list): Список словарей с информацией об отсутствующих сотрудниках, включая ПИН и имя.
            data_for_date (str): Дата, за которую предоставлены данные, в формате 'YYYY-MM-DD'.

    Примеры:
        GET /api/attendance/stats/?date=2024-07-20
        GET /api/attendance/stats/?pin=123456

    Примечание:
        Ответ кэшируется на 1 час, а информация о государственных праздниках кэшируется на 1 минуту.
    """

    permission_classes = [permissions.IsAuthenticatedOrAPIKey]

    @swagger_auto_schema(
        operation_summary="Получить список людей об их присутствии",
        operation_description="View для получения статистики о посещаемости персонала.",
        tags=["Attendance & Statistics"],
        responses={
            200: openapi.Response(
                description="Successful response",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "department_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "total_staff_count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "present_staff_count": openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        "absent_staff_count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "present_between_9_to_18": openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        "present_data": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "staff_pin": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "name": openapi.Schema(type=openapi.TYPE_STRING),
                                    "minutes_present": openapi.Schema(
                                        type=openapi.TYPE_NUMBER
                                    ),
                                    "individual_percentage": openapi.Schema(
                                        type=openapi.TYPE_NUMBER
                                    ),
                                },
                            ),
                        ),
                        "absent_data": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "staff_pin": openapi.TYPE_STRING,
                                    "name": openapi.Schema(type=openapi.TYPE_STRING),
                                },
                            ),
                        ),
                        "data_for_date": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            404: "Not Found",
            500: "Internal Server Error",
        },
        manual_parameters=[
            openapi.Parameter(
                name="X-API-KEY",
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                required=False,
                description="API ключ для аутентификации (альтернатива JWT токену).",
            ),
            openapi.Parameter(
                "date",
                openapi.IN_QUERY,
                description="Date in 'YYYY-MM-DD' format.",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "pin",
                openapi.IN_QUERY,
                description="Staff PIN.",
                type=openapi.TYPE_STRING,
            ),
        ],
    )
    def get(self, request):
        logger.info("Received request for staff attendance stats.")

        date_param = request.query_params.get(
            "date", timezone.now().date().strftime("%Y-%m-%d")
        )
        date_param = datetime.datetime.strptime(date_param, "%Y-%m-%d").date()
        pin_param = request.query_params.get("pin", None)

        logger.debug(f"Parsed date_param: {date_param}, pin_param: {pin_param}")

        try:
            target_date = self.get_last_working_day(date_param)
            next_date = target_date + datetime.timedelta(days=1)
            cache_key = f"staff_attendance_stats_{target_date}_{pin_param}"

            logger.debug(f"Generated cache_key: {cache_key}")

            cached_data = get_cache(
                cache_key,
                query=lambda: self.query_data(target_date, next_date, pin_param),
                timeout=5 * 60,
            )

            logger.info("Successfully retrieved staff attendance data.")
            return Response(cached_data)

        except Exception as e:
            logger.error(f"Error while processing request: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_last_working_day(self, date: datetime.date) -> datetime.date:
        """
        Определение последнего рабочего дня, с учетом выходных и государственных праздников.

        Args:
            date (datetime.date): Дата, для которой нужно найти последний рабочий день.

        Returns:
            datetime.date: Последний рабочий день.
        """
        logger.debug(f"Calculating last working day for date: {date}")

        holidays = (
            get_cache(
                "public_holidays",
                query=lambda: list(models.PublicHoliday.objects.all()),
                timeout=10 * 6,
            )
            or []
        )
        holiday_dates = {
            holiday.date: holiday.is_working_day for holiday in holidays if holiday
        }

        while date.weekday() >= 5 or (
            date in holiday_dates and not holiday_dates[date]
        ):
            logger.debug(f"{date} is not a working day, moving to previous day.")
            date -= datetime.timedelta(days=1)

        logger.debug(f"Last working day determined: {date}")
        return date

    def query_data(
        self,
        target_date: datetime.date,
        _next_date: datetime.date,
        pin_param: str | None,
    ) -> dict:
        """
        Запрашивает данные по целевой дате и отделу (или сотруднику).

        Args:
            target_date (datetime.date): Целевая дата.
            next_date (datetime.date): Следующая дата после целевой.
            pin_param (str, optional): ID родительского или дочернего отдела.

        Returns:
            dict: Данные о сотрудниках, их посещаемости и статистике.
        """
        logger.info(
            f"Querying data for target_date: {target_date}, pin_param: {pin_param}"
        )

        department_name = "Unknown Department"
        staff_queryset = None

        parent_department = models.ParentDepartment.objects.filter(id=pin_param).first()
        child_department = models.ChildDepartment.objects.filter(id=pin_param).first()

        match (parent_department, child_department):
            case (parent, None) if parent:
                staff_queryset = models.Staff.objects.filter(
                    department__parent_id=parent.id
                ).select_related("department")
                department_name = parent.name
            case (None, child) if child:
                staff_queryset = models.Staff.objects.filter(
                    department=child
                ).select_related("department")
                department_name = child.name
            case _:
                staff_queryset = models.Staff.objects.filter(
                    Q(department__parent__name__icontains="AUP")
                    | Q(department__parent__name__icontains="АУП")
                ).select_related("department")
                department_name = (
                    staff_queryset.first().department.parent.name
                    if staff_queryset.exists()
                    else "Unknown Department"
                )

        target_date_for_filter = target_date + datetime.timedelta(days=1)
        staff_queryset = staff_queryset.select_related("department__parent").only(
            "pin",
            "name",
            "surname",
            "department_id",
            "department__name",
            "department__parent__name",
        )
        staff_members = list(staff_queryset)

        if not staff_members:
            return {
                "department_name": department_name,
                "total_staff_count": 0,
                "present_staff_count": 0,
                "absent_staff_count": 0,
                "present_between_9_to_18": 0,
                "present_data": [],
                "absent_data": [],
                "data_for_date": target_date.strftime("%Y-%m-%d"),
            }

        staff_attendance_queryset = (
            models.StaffAttendance.objects.filter(
                date_at=target_date_for_filter, staff__in=staff_members
            )
            .select_related("staff")
            .only(
                "first_in",
                "last_out",
                "area_name_in",
                "area_name_out",
                "staff__pin",
                "staff__name",
                "staff__surname",
            )
        )

        attendance_records = list(staff_attendance_queryset)
        present_staff_records = [
            record for record in attendance_records if record.first_in is not None
        ]
        attendance_by_pin = {
            record.staff.pin: record for record in present_staff_records
        }
        present_staff_pins = set(attendance_by_pin.keys())

        total_staff_count = len(staff_members)
        absent_staff_count = total_staff_count - len(present_staff_pins)

        present_between_9_to_18 = 0
        for record in present_staff_records:
            first_in_time = record.first_in.time()
            if datetime.time(8, 0) <= first_in_time <= datetime.time(19, 0):
                present_between_9_to_18 += 1

        present_data, absent_data = self.get_attendance_data(
            staff_members, attendance_by_pin
        )

        logger.info(f"Data query successful for department: {department_name}")

        return {
            "department_name": department_name,
            "total_staff_count": total_staff_count,
            "present_staff_count": len(present_data),
            "absent_staff_count": absent_staff_count,
            "present_between_9_to_18": present_between_9_to_18,
            "present_data": present_data,
            "absent_data": absent_data,
            "data_for_date": target_date.strftime("%Y-%m-%d"),
        }

    def get_attendance_data(self, staff_members, attendance_by_pin):
        logger.debug("Generating attendance data.")
        present_data = []
        absent_data = []
        total_minutes = 8 * 60
        for staff in staff_members:
            attendance = attendance_by_pin.get(staff.pin)
            if attendance:
                minutes_present = (
                    (attendance.last_out - attendance.first_in).total_seconds() / 60
                    if attendance.last_out
                    else 0
                )
                individual_percentage = (minutes_present / total_minutes) * 100
                present_data.append(
                    {
                        "staff_pin": staff.pin,
                        "name": f"{staff.surname} {staff.name}",
                        "minutes_present": round(minutes_present, 2),
                        "individual_percentage": round(individual_percentage, 2),
                    }
                )
                continue

            absent_data.append(
                {
                    "staff_pin": staff.pin,
                    "name": f"{staff.surname} {staff.name}",
                }
            )

        logger.info("Attendance data generation complete.")
        return present_data, absent_data


@swagger_auto_schema(
    method="get",
    operation_summary="Получить данные локаций для отображения на карте",
    operation_description=(
        "Эндпоинт для получения данных локаций с информацией о посещениях для заданной даты."
        " Опционально можно получить данные о сотрудниках, если задан параметр `employees=true`."
    ),
    tags=["Locations"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            name="date_at",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            format=openapi.FORMAT_DATE,
            description="Дата для фильтрации посещений (формат YYYY-MM-DD). Если не указана, используется текущая дата.",
            required=False,
        ),
        openapi.Parameter(
            name="employees",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_BOOLEAN,
            description="Флаг для включения данных о сотрудниках (true/false). По умолчанию false.",
            required=False,
        ),
    ],
    responses={
        200: openapi.Response(
            description="Успешный ответ с данными локаций для отображения на карте.",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "name": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Название локации"
                        ),
                        "address": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Адрес локации"
                        ),
                        "lat": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Широта",
                        ),
                        "lng": openapi.Schema(
                            type=openapi.TYPE_NUMBER,
                            format=openapi.FORMAT_FLOAT,
                            description="Долгота",
                        ),
                        "employees": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Количество посещений или сотрудников (если указано employees=true)",
                            default=0,
                        ),
                    },
                ),
            ),
        ),
        500: openapi.Response(description="Внутренняя ошибка сервера"),
    },
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def map_location(request):
    """
    Возвращает данные о локациях и количестве сотрудников и студентов на основе турникетов и занятий за указанную дату.

    Args:
        request (HttpRequest): HTTP-запрос с параметром `date_at` для фильтрации данных и параметром `employees` для включения данных о сотрудниках.

    Returns:
        JsonResponse: JSON-ответ с данными о локациях, если запрос успешен, либо сообщение об ошибке.
    """
    try:
        date_at_str = request.GET.get("date_at", None)
        employees_required = request.GET.get("employees", "false").lower() == "true"

        if date_at_str:
            try:
                date_at = datetime.datetime.strptime(date_at_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(f"Incorrect date format: {date_at_str}")
                return Response(
                    {"error": "Incorrect Date format, please use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            date_at = datetime.datetime.now().date()

        logger.info(f"Using date: {date_at}")

        cache_key = f"map_location_{date_at}_{employees_required}"

        def generate_map_data():
            locations = models.ClassLocation.objects.only(
                "address", "name", "latitude", "longitude"
            )
            return utils.generate_map_data(
                locations,
                date_at,
                search_staff_attendance=employees_required,
                filter_empty=not employees_required,
            )

        result = get_cache(
            cache_key,
            query=generate_map_data,
            timeout=5 * 60,
        )

        logger.info(f"Generated map data with employees: {result}")
        return Response(result, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Critical error in map_location: {str(e)}", exc_info=True)
        return Response(
            {"error": "A critical error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="GET",
    operation_summary="Список локаций для занятий",
    operation_description=(
        "**Без latitude/longitude:** все локации (id, name, address, latitude, longitude). "
        "Поле distance отсутствует.\n\n"
        "**С latitude и longitude:** фронт шлёт координаты, ответ — «в локации или нет». "
        "Только локации, где d ≤ R_loc: d — Haversine (user, pin) в м, R_loc из кэша/БД. "
        "Сортировка по d. В элементе: distance = d (м, 2 знака). Если ни одна не подходит → 404."
    ),
    tags=["Locations"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            name="latitude",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_NUMBER,
            format=openapi.FORMAT_FLOAT,
            required=False,
            description="Широта пользователя (WGS84). Для поиска по радиусу нужны оба: latitude и longitude.",
            example=43.246871,
        ),
        openapi.Parameter(
            name="longitude",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_NUMBER,
            format=openapi.FORMAT_FLOAT,
            required=False,
            description="Долгота пользователя (WGS84). Для поиска по радиусу нужны оба: latitude и longitude.",
            example=76.944923,
        ),
    ],
    responses={
        200: openapi.Response(
            description="locations. Без lat/lon: все, без distance. С lat/lon: d ≤ R_loc, distance = Haversine (м).",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                required=["locations"],
                properties={
                    "locations": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description="При lat/lon: в радиусе (d ≤ R_loc), distance — Haversine в м. Без lat/lon: все локации.",
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            required=["id", "name", "address", "latitude", "longitude"],
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    description="ID локации",
                                ),
                                "name": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="Название",
                                ),
                                "address": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="Адрес",
                                ),
                                "latitude": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format=openapi.FORMAT_FLOAT,
                                    description="Широта точки локации",
                                ),
                                "longitude": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format=openapi.FORMAT_FLOAT,
                                    description="Долгота точки локации",
                                ),
                                "distance": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format=openapi.FORMAT_FLOAT,
                                    description=(
                                        "Только при lat/lon. Haversine(пользователь, pin) в метрах, 2 знака. "
                                        "Погрешность на практике — точность GPS (5–15 м у смартфона)."
                                    ),
                                ),
                            },
                        ),
                    ),
                },
            ),
        ),
        404: openapi.Response(
            description=(
                "При lat/lon: нет локаций с d ≤ R_loc — {message, detail}. "
                'Пустая БД по локациям — {error: "No locations available in database"}.'
            ),
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Системное: напр. «Ближайшая локация 85.2 м, превышен лимит 70 м».",
                    ),
                    "detail": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Для фронта: «Ничего не найдено».",
                    ),
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="При пустой БД: «No locations available in database».",
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description=(
                "Параметры отсутствуют или неверный формат. "
                "error, detail: «Широта обязательна», «Долгота обязательна», "
                "«Широта и долгота обязательны», «Invalid latitude or longitude format. Expected numbers.»"
            ),
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Код/текст ошибки",
                    ),
                    "detail": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение для пользователя",
                    ),
                },
            ),
        ),
        500: openapi.Response(
            description="Внутренняя ошибка сервера",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Описание ошибки",
                    ),
                },
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def lesson_locations(request):
    """Список локаций: все либо только в приёмном радиусе R_loc.

    Без lat/lon: все локации (id, name, address, latitude, longitude).
    Поле distance не возвращается.

    С lat/lon: только локации, где d ≤ R_loc. d — Haversine (user, pin) в м,
    R_loc из кэша или ClassLocation.acceptance_radius_m. Сортировка по d.
    В ответе: distance = round(d, 2) (м). Погрешность — точность GPS (5–15 м).

    Args:
        request: GET; опционально latitude, longitude (WGS84, числа).

    Returns:
        Response: {locations: [...]}; при lat/lon и отсутствии подходящих — 404.
    """

    def _not_found(system_message: str):
        return Response(
            {"message": system_message, "detail": "Ничего не найдено"},
            status=status.HTTP_404_NOT_FOUND,
        )

    log_ll = logging.getLogger("monitoring_app.lesson_locations")
    log_ll_nf = logging.getLogger("monitoring_app.lesson_locations.not_found")

    try:
        latitude_param = request.GET.get("latitude")
        longitude_param = request.GET.get("longitude")

        def _is_empty(val):
            return val is None or (isinstance(val, str) and val.strip() == "")

        lat_empty = _is_empty(latitude_param)
        lon_empty = _is_empty(longitude_param)

        if latitude_param is None and longitude_param is None:
            pass
        elif lat_empty and lon_empty:
            log_ll.warning("MISSING both lat and lon")
            return Response(
                {
                    "error": "Широта и долгота обязательны",
                    "detail": "Широта и долгота обязательны",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif lat_empty:
            log_ll.warning("MISSING latitude lon=%s", longitude_param)
            return Response(
                {"error": "Широта обязательна", "detail": "Широта обязательна"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif lon_empty:
            log_ll.warning("MISSING longitude lat=%s", latitude_param)
            return Response(
                {"error": "Долгота обязательна", "detail": "Долгота обязательна"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if latitude_param is not None and longitude_param is not None:
            log_ll.info("request lat=%s lon=%s", latitude_param, longitude_param)
            try:
                latitude = float(latitude_param)
                longitude = float(longitude_param)
            except (ValueError, TypeError):
                log_ll.warning("INVALID lat=%s lon=%s", latitude_param, longitude_param)
                return Response(
                    {
                        "error": "Invalid latitude or longitude format. Expected numbers.",
                        "detail": "Неверный формат. Ожидаются числа.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            all_locations = models.ClassLocation.objects.filter(
                latitude__isnull=False, longitude__isnull=False
            ).only("id", "name", "address", "latitude", "longitude")

            if not all_locations.exists():
                log_ll.warning("NO_LOCATIONS_IN_DB")
                return Response(
                    {"error": "No locations available in database"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            radii = get_class_location_cache().get("location_acceptance_radius_m", {})
            within = []
            min_overall = float("inf")
            nearest_loc = None

            for loc in all_locations:
                d = utils.calculate_distance_haversine(
                    latitude, longitude, loc.latitude, loc.longitude
                )
                R = radii.get(loc.id, DEFAULT_ACCEPTANCE_RADIUS_M)
                if d < min_overall:
                    min_overall = d
                    nearest_loc = loc
                if d <= R:
                    within.append((d, loc, R))

            within.sort(key=lambda x: x[0])

            if not within:
                R_n = (
                    radii.get(nearest_loc.id, DEFAULT_ACCEPTANCE_RADIUS_M)
                    if nearest_loc is not None
                    else DEFAULT_ACCEPTANCE_RADIUS_M
                )
                nearest_name = nearest_loc.name if nearest_loc else "N/A"
                loc_lat = nearest_loc.latitude if nearest_loc else 0
                loc_lon = nearest_loc.longitude if nearest_loc else 0
                loc_id = nearest_loc.id if nearest_loc else 0
                log_ll.warning(
                    "NOT_FOUND user(%.6f,%.6f) nearest_id=%d d=%.1fm R=%dm",
                    latitude,
                    longitude,
                    loc_id,
                    min_overall,
                    R_n,
                )
                log_ll_nf.warning(
                    "Haversine: d(user,loc)<=R => in_radius | "
                    "user(lat=%.6f,lon=%.6f) nearest=%s[id=%d](lat=%.6f,lon=%.6f) "
                    "d=%.1fm R=%dm => d>R NOT_FOUND",
                    latitude,
                    longitude,
                    nearest_name,
                    loc_id,
                    loc_lat,
                    loc_lon,
                    min_overall,
                    R_n,
                )
                return _not_found(
                    f"Ближайшая локация {min_overall:.1f} м, превышен лимит {R_n} м"
                )

            log_ll.info(
                "FOUND %d | %s",
                len(within),
                ", ".join(f"{loc.name}({d:.1f}m)" for d, loc, _ in within),
            )

            locations_data = [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "address": loc.address,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "distance": round(d, 2),
                }
                for d, loc, R in within
            ]

            return Response(
                {"locations": locations_data},
                status=status.HTTP_200_OK,
            )

        log_ll.info("request all locations")
        locations = models.ClassLocation.objects.only(
            "id", "name", "address", "latitude", "longitude"
        ).order_by("name")
        locations_data = [
            {
                "id": loc.id,
                "name": loc.name,
                "address": loc.address,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
            }
            for loc in locations
        ]
        log_ll.info("returned %d locations", len(locations_data))

        return Response(
            {"locations": locations_data},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        log_ll.error(f"Critical error in lesson_locations: {str(e)}", exc_info=True)
        return Response(
            {"error": "A critical error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


_CLASSLOCATION_FIELDS = (
    "id",
    "name",
    "address",
    "latitude",
    "longitude",
    "acceptance_radius_m",
)

_classlocation_item_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=["name", "address", "latitude", "longitude"],
    properties={
        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Название"),
        "address": openapi.Schema(type=openapi.TYPE_STRING, description="Адрес"),
        "latitude": openapi.Schema(
            type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT, description="Широта"
        ),
        "longitude": openapi.Schema(
            type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT, description="Долгота"
        ),
        "acceptance_radius_m": openapi.Schema(
            type=openapi.TYPE_INTEGER,
            nullable=True,
            description="Приёмный радиус (м), опционально",
        ),
    },
)

_classlocation_list_response = openapi.Response(
    description="Список локаций",
    schema=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "results": openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "name": openapi.Schema(type=openapi.TYPE_STRING),
                        "address": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
                        "acceptance_radius_m": openapi.Schema(
                            type=openapi.TYPE_INTEGER, nullable=True
                        ),
                    },
                ),
            ),
        },
    ),
)


@swagger_auto_schema(
    method="get",
    operation_summary="Список локаций занятий (CRUD)",
    operation_description="Возвращает все локации: id, название, адрес, широта, долгота, приёмный радиус (м). Один запрос к БД.",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
    ],
    responses={200: _classlocation_list_response},
)
@swagger_auto_schema(
    method="post",
    operation_summary="Создать одну или несколько локаций",
    operation_description="Тело: один объект или массив объектов. При массовом создании кэш локаций инвалидируется.",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_ARRAY,
        description="Один объект или массив объектов: name, address, latitude, longitude, acceptance_radius_m (опционально).",
        items=_classlocation_item_schema,
    ),
    responses={
        201: openapi.Response(
            description="Создано",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "results": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT),
                    ),
                },
            ),
        ),
        400: openapi.Response(description="Ошибка валидации"),
    },
)
@swagger_auto_schema(
    method="delete",
    operation_summary="Массовое удаление локаций",
    operation_description="Query-параметр ids: список ID через запятую, например ?ids=1,2,3.",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            name="ids",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="ID локаций через запятую (например 1,2,3)",
        ),
    ],
    responses={
        200: openapi.Response(description="Удалено"),
        400: openapi.Response(description="Не указаны ids"),
    },
)
@api_view(["GET", "POST", "DELETE"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def class_location_list_create(request):
    """GET: список (кэш 1 ч, один запрос .values()). POST/DELETE: инвалидация + прогрев списка и таска радиусов."""
    if request.method == "GET":
        data = Cache.get(CLASS_LOCATION_LIST_CACHE_KEY)
        if data is None:
            data = list(
                models.ClassLocation.objects.order_by("id").values(
                    "id",
                    "name",
                    "address",
                    "latitude",
                    "longitude",
                    "acceptance_radius_m",
                )
            )
            Cache.set(
                CLASS_LOCATION_LIST_CACHE_KEY,
                data,
                CLASS_LOCATION_LIST_CACHE_TTL,
            )
        return Response({"results": data}, status=status.HTTP_200_OK)

    if request.method == "POST":
        try:
            body = request.data
        except Exception:
            body = None
        if body is None:
            return Response(
                {"error": "Request body is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        is_list = isinstance(body, list)
        items = body if is_list else [body]
        serializer = serializers.ClassLocationSerializer(data=items, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated = serializer.validated_data
        if not validated or not isinstance(validated, (list, tuple)):
            return Response(
                {"error": "At least one item required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with _db_atomic():
            created = []
            for d in validated:
                obj = models.ClassLocation.objects.create(
                    name=d["name"],
                    address=d["address"],
                    latitude=d["latitude"],
                    longitude=d["longitude"],
                    acceptance_radius_m=d.get("acceptance_radius_m"),
                )
                created.append(obj)
        if len(created) > 0:
            invalidate_class_location_cache_impl()
        result = [
            {
                "id": o.id,
                "name": o.name,
                "address": o.address,
                "latitude": o.latitude,
                "longitude": o.longitude,
                "acceptance_radius_m": getattr(o, "acceptance_radius_m", None),
            }
            for o in created
        ]
        return Response({"results": result}, status=status.HTTP_201_CREATED)

    if request.method == "DELETE":
        ids_param = request.query_params.get("ids") or request.query_params.get("id")
        if not ids_param:
            return Response(
                {"error": "Query parameter 'ids' is required (e.g. ids=1,2,3)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            id_list = [int(x.strip()) for x in ids_param.split(",") if x.strip()]
        except ValueError:
            return Response(
                {"error": "ids must be comma-separated integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not id_list:
            return Response(
                {"error": "At least one id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = models.ClassLocation.objects.filter(id__in=id_list).delete()
        return Response(
            {"deleted": deleted, "ids": id_list},
            status=status.HTTP_200_OK,
        )


@swagger_auto_schema(
    method="get",
    operation_summary="Одна локация по ID",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            "id", openapi.IN_PATH, type=openapi.TYPE_INTEGER, description="ID локации"
        ),
    ],
    responses={
        200: _classlocation_list_response,
        404: openapi.Response(description="Не найдено"),
    },
)
@swagger_auto_schema(
    method="patch",
    operation_summary="Обновить одну локацию",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            "id", openapi.IN_PATH, type=openapi.TYPE_INTEGER, description="ID локации"
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "name": openapi.Schema(type=openapi.TYPE_STRING),
            "address": openapi.Schema(type=openapi.TYPE_STRING),
            "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
            "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
            "acceptance_radius_m": openapi.Schema(
                type=openapi.TYPE_INTEGER, nullable=True
            ),
        },
    ),
    responses={
        200: _classlocation_list_response,
        404: openapi.Response(description="Не найдено"),
    },
)
@swagger_auto_schema(
    method="delete",
    operation_summary="Удалить одну локацию",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            "id", openapi.IN_PATH, type=openapi.TYPE_INTEGER, description="ID локации"
        ),
    ],
    responses={
        200: openapi.Response(description="Удалено"),
        404: openapi.Response(description="Не найдено"),
    },
)
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def class_location_detail(request, pk):
    """GET/PATCH/DELETE одной локации по pk. Кэш инвалидируется через signal при save/delete."""
    loc = get_object_or_404(
        models.ClassLocation.objects.only(*_CLASSLOCATION_FIELDS),
        pk=pk,
    )
    if request.method == "GET":
        return Response(
            {
                "id": loc.id,
                "name": loc.name,
                "address": loc.address,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "acceptance_radius_m": loc.acceptance_radius_m,
            },
            status=status.HTTP_200_OK,
        )
    if request.method == "PATCH":
        serializer = serializers.ClassLocationSerializer(
            loc, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    if request.method == "DELETE":
        loc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


_classlocation_bulk_update_schema = openapi.Schema(
    type=openapi.TYPE_ARRAY,
    items=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["id"],
        properties={
            "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID локации"),
            "name": openapi.Schema(type=openapi.TYPE_STRING),
            "address": openapi.Schema(type=openapi.TYPE_STRING),
            "latitude": openapi.Schema(type=openapi.TYPE_NUMBER),
            "longitude": openapi.Schema(type=openapi.TYPE_NUMBER),
            "acceptance_radius_m": openapi.Schema(
                type=openapi.TYPE_INTEGER, nullable=True
            ),
        },
    ),
)


@swagger_auto_schema(
    method="patch",
    operation_summary="Массовое обновление локаций",
    operation_description="Тело: массив объектов с обязательным полем id. После обновления кэш инвалидируется.",
    tags=["ClassLocation"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ (альтернатива JWT).",
        ),
    ],
    request_body=_classlocation_bulk_update_schema,
    responses={
        200: openapi.Response(
            description="Обновлено",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "updated": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "results": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT),
                    ),
                },
            ),
        ),
        400: openapi.Response(description="Ошибка валидации"),
    },
)
@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def class_location_bulk_update(request):
    """Массовое обновление: bulk_update + инвалидация кэша."""
    try:
        body = request.data
    except Exception:
        body = None
    if body is None:
        return Response(
            {"error": "Body must be a non-empty array of objects with 'id'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(body, list):
        body = [body] if isinstance(body, dict) and "id" in body else []
    if not body:
        return Response(
            {"error": "Body must be a non-empty array of objects with 'id'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    ids = []
    for item in body:
        raw_id = item.get("id")
        if raw_id is None:
            return Response(
                {"error": "Each item must have integer 'id'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            return Response(
                {"error": "Each item must have integer 'id'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    unique_ids = list(dict.fromkeys(ids))
    qs = list(
        models.ClassLocation.objects.only(*_CLASSLOCATION_FIELDS).filter(id__in=unique_ids)
    )
    found_ids = {o.id for o in qs}
    missing = [i for i in unique_ids if i not in found_ids]
    if missing:
        return Response(
            {"error": "Some ids not found", "missing_ids": missing},
            status=status.HTTP_404_NOT_FOUND,
        )
    by_id = {o.id: o for o in qs}
    update_fields = ["name", "address", "latitude", "longitude", "acceptance_radius_m"]
    for raw in body:
        obj = by_id.get(int(raw["id"]))
        if not obj:
            continue
        for f in update_fields:
            if f in raw:
                setattr(obj, f, raw[f])
    with _db_atomic():
        models.ClassLocation.objects.bulk_update(qs, update_fields)
    invalidate_class_location_cache_impl()
    results = [
        {
            "id": o.id,
            "name": o.name,
            "address": o.address,
            "latitude": o.latitude,
            "longitude": o.longitude,
            "acceptance_radius_m": o.acceptance_radius_m,
        }
        for o in qs
    ]
    return Response({"updated": len(qs), "results": results}, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить ID всех корневых (root) подразделений",
    operation_description="Возвращает список ID из ChildDepartment, где parent IS NULL.",
    tags=["Departments"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Ок",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="ID корневого подразделения (ChildDepartment).",
                ),
            ),
        ),
        404: openapi.Response(
            description="Не удалось найти корни",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_parent_id(request):
    """
    Получить ID всех родительских департаментов.

    Этот метод возвращает список всех ID родительских департаментов.

    Возвращаемые данные:
    - Список ID родительских департаментов.

    Возможные ошибки:
    - 404: Департаменты не найдены.

    Пример ответа:
    - 200: [1, 2, 3, ...]
    - 404: {"error": "Не удалось найти департаменты."}
    """
    logger.info("Request received to get parent department IDs.")

    cache_key = "parent_department_ids"

    def fetch_parent_ids():
        roots = (
            models.ChildDepartment.objects.filter(parent__isnull=True)
            .order_by("id")
            .values_list("id", flat=True)
        )
        return [str(pk) for pk in roots]

    try:
        root_ids = get_cache(
            cache_key,
            query=fetch_parent_ids,
            timeout=30 * 60,
        )

        if not root_ids:
            return Response(
                {"error": "Корни не найдены"}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(root_ids, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="GET",
    operation_summary="Сводная информация о департаменте",
    operation_description="Метод для получения сводной информации о департаменте и его дочерних подразделениях с количеством сотрудников.",
    tags=["Departments"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Успешный запрос. Возвращается сводная информация о департаменте и его дочерних подразделениях.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "name": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Название департамента.",
                    ),
                    "date_of_creation": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        format="date-time",
                        description="Дата создания департамента.",
                    ),
                    "child_departments": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "child_id": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="ID дочернего подразделения.",
                                ),
                                "name": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="Название дочернего подразделения.",
                                ),
                                "date_of_creation": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format="date-time",
                                    description="Дата создания дочернего подразделения.",
                                ),
                                "parent": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="ID родительского департамента.",
                                ),
                            },
                        ),
                        description="Список дочерних подразделений департамента.",
                    ),
                    "total_staff_count": openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description="Общее количество сотрудников в департаменте и его дочерних подразделениях.",
                    ),
                },
            ),
        ),
        404: "Департамент не найден.",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def department_summary(request, parent_department_id):
    cache_key = f"department_summary_{parent_department_id}"
    logger.info(
        f"Request received for department summary with ID {parent_department_id}"
    )

    if not models.ChildDepartment.objects.filter(id=parent_department_id).exists():
        logger.warning(f"Department with ID {parent_department_id} not found")
        return Response(
            status=status.HTTP_404_NOT_FOUND,
            data={"message": f"Department with ID {parent_department_id} not found"},
        )

    try:

        def calculate_staff_count(department: models.ChildDepartment) -> int:
            rows = list(models.ChildDepartment.objects.values_list("id", "parent_id"))

            children_by_parent = {}
            for cid, pid in rows:
                children_by_parent.setdefault(pid, []).append(cid)

            visited = set()
            stack = [department.id]
            subtree_ids = []

            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                subtree_ids.append(cur)
                stack.extend(children_by_parent.get(cur, []))

            total = (
                models.Staff.objects.filter(department_id__in=subtree_ids)
                .values("id")
                .distinct()
                .count()
            )
            return total

        parent_department = get_object_or_404(
            models.ChildDepartment, id=parent_department_id
        )
        logger.info(
            f"Department found: {parent_department.name} (ID: {parent_department_id})"
        )
        parent_department_id = str(parent_department_id).zfill(5)
        total_staff_count = calculate_staff_count(parent_department)

        child_departments_data = models.ChildDepartment.objects.filter(
            parent=parent_department
        )
        child_departments_data_serialized = serializers.ChildDepartmentSerializer(
            child_departments_data, many=True
        ).data

        data = {
            "name": parent_department.name,
            "date_of_creation": parent_department.date_of_creation,
            "child_departments": child_departments_data_serialized,
            "total_staff_count": total_staff_count,
        }

        logger.debug(f"Caching department summary data with key: {cache_key}")
        cached_data = get_cache(
            cache_key, query=lambda: data, timeout=5 * 60, cache=Cache
        )

        logger.info(f"Returning summary data for department ID {parent_department_id}")
        return Response(cached_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error while generating department summary: {str(e)}")
        return Response(data={"message": str(e)}, status=status.HTTP_404_NOT_FOUND)


def _fetch_root_departments_data():
    """
    Внутренняя функция для получения данных корневых департаментов.
    Может использоваться как в API endpoint, так и в preload.
    """
    all_departments = list(
        models.ChildDepartment.objects.only(
            "id", "parent_id", "name", "date_of_creation"
        ).values_list("id", "parent_id", "name", "date_of_creation")
    )

    dept_by_id = {}
    children_by_parent = {}
    root_ids = []

    for dept_id, parent_id, name, date_of_creation in all_departments:
        dept_by_id[dept_id] = {
            "id": dept_id,
            "name": name,
            "date_of_creation": date_of_creation,
        }
        if parent_id is None:
            root_ids.append(dept_id)
        else:
            children_by_parent.setdefault(parent_id, []).append(dept_id)

    if not root_ids:
        return {
            "departments": [],
            "total_staff_count": 0,
        }

    root_ids.sort()

    subtree_ids_by_root = {}
    for root_id in root_ids:
        visited = set()
        stack = [root_id]
        subtree_ids = []

        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            subtree_ids.append(cur)
            stack.extend(children_by_parent.get(cur, []))

        subtree_ids_by_root[root_id] = subtree_ids

    all_subtree_ids = []
    for subtree_ids in subtree_ids_by_root.values():
        all_subtree_ids.extend(subtree_ids)

    unique_subtree_ids = list(set(all_subtree_ids))

    staff_counts = (
        models.Staff.objects.filter(department_id__in=unique_subtree_ids)
        .values("department_id")
        .annotate(count=Count("id", distinct=True))
    )

    staff_count_by_dept = {
        item["department_id"]: item["count"] for item in staff_counts
    }

    all_child_dept_ids = []
    for children in children_by_parent.values():
        all_child_dept_ids.extend(children)

    child_depts_by_parent = {}
    if all_child_dept_ids:
        child_depts = models.ChildDepartment.objects.filter(
            id__in=all_child_dept_ids
        ).only("id", "name", "date_of_creation", "parent_id")

        for child in child_depts:
            parent_id = child.parent_id
            if parent_id:
                child_depts_by_parent.setdefault(parent_id, []).append(child)

    departments_data = []
    total_staff_count = 0

    for root_id in root_ids:
        dept = dept_by_id[root_id]
        subtree_ids = subtree_ids_by_root[root_id]
        dept_total = sum(staff_count_by_dept.get(dept_id, 0) for dept_id in subtree_ids)
        total_staff_count += dept_total

        has_children = bool(children_by_parent.get(root_id))

        child_depts = child_depts_by_parent.get(root_id, [])
        child_departments_serialized = [
            {
                "child_id": str(child.id),
                "name": child.name,
                "date_of_creation": child.date_of_creation,
                "parent": str(root_id),
            }
            for child in child_depts
        ]

        departments_data.append(
            {
                "child_id": str(root_id),
                "name": dept["name"],
                "date_of_creation": dept["date_of_creation"],
                "parent": "",
                "has_child_departments": has_children,
                "total_staff_count": dept_total,
                "child_departments": child_departments_serialized,
            }
        )

    return {
        "departments": departments_data,
        "total_staff_count": total_staff_count,
    }


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить все корневые департаменты одним запросом",
    operation_description="Оптимизированный endpoint для получения всех корневых департаментов с их сводной информацией одним запросом. Используется для быстрой загрузки главной страницы.",
    tags=["Departments"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Успешный ответ",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "departments": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "child_id": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="ID корневого департамента",
                                ),
                                "name": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="Название департамента",
                                ),
                                "date_of_creation": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format="date-time",
                                    description="Дата создания",
                                ),
                                "parent": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    description="ID родительского департамента (всегда пусто для корневых)",
                                ),
                                "has_child_departments": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN,
                                    description="Есть ли дочерние подразделения",
                                ),
                                "total_staff_count": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    description="Общее количество сотрудников",
                                ),
                                "child_departments": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            "child_id": openapi.Schema(
                                                type=openapi.TYPE_STRING
                                            ),
                                            "name": openapi.Schema(
                                                type=openapi.TYPE_STRING
                                            ),
                                            "date_of_creation": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                format="date-time",
                                            ),
                                            "parent": openapi.Schema(
                                                type=openapi.TYPE_STRING
                                            ),
                                        },
                                    ),
                                    description="Список дочерних подразделений",
                                ),
                            },
                        ),
                    ),
                    "total_staff_count": openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description="Общее количество сотрудников во всех корневых департаментах",
                    ),
                },
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def root_departments_batch(request):
    """
    Получить все корневые департаменты одним оптимизированным запросом.
    Используется для быстрой загрузки главной страницы вместо множественных запросов.
    """
    cache_key = "root_departments_batch"
    logger.info("Request received for root departments batch")

    try:
        cached_data = get_cache(
            cache_key,
            query=_fetch_root_departments_data,
            timeout=15 * 60,
        )

        logger.info("Returning root departments batch data")
        return Response(cached_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error while generating root departments batch: {str(e)}")
        return Response(
            data={"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    method="get",
    operation_summary="Получить описание подотдела",
    operation_description="Получите подробную информацию о подотделе и его сотрудниках.",
    tags=["Departments"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            name="child_department_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            description="ID подотдела",
            required=True,
        ),
    ],
    responses={
        200: openapi.Response(
            description="Сведения о подотделе и данные о персонале",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "child_department": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "name": openapi.Schema(type=openapi.TYPE_STRING),
                            "date_of_creation": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                format=openapi.FORMAT_DATETIME,
                            ),
                            "parent": openapi.Schema(type=openapi.TYPE_INTEGER),
                        },
                    ),
                    "staff_count": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "staff_data": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        additional_properties=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "FIO": openapi.Schema(type=openapi.TYPE_STRING),
                                "date_of_creation": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATETIME,
                                ),
                                "avatar": openapi.Schema(type=openapi.TYPE_STRING),
                                "positions": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(type=openapi.TYPE_STRING),
                                ),
                            },
                        ),
                    ),
                },
            ),
        ),
        404: "Not Found: Если подотдела не существует.",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def child_department_detail(request, child_department_id):
    """
    Получите подробную информацию о дочернем отделе вместе с его сотрудниками.

    Args:
    запрос: объект запроса.
    child_department_id (int): идентификатор дочернего отдела, который требуется получить.

    Returns:
    Ответ: ответ, содержащий сведения о дочернем отделе и данные о сотрудниках.

    Raises:
    Http404: Если дочерний отдел не существует.
    """
    logger.info(
        f"Request received for child department detail with ID {child_department_id}"
    )

    cache_key = f"child_department_detail_{child_department_id}"

    def fetch_child_department_data():
        try:
            child_department = models.ChildDepartment.objects.get(
                id=child_department_id
            )
            logger.info(
                f"Found child department: {child_department.name} (ID: {child_department_id})"
            )
        except models.ChildDepartment.DoesNotExist:
            logger.warning(f"Child department with ID {child_department_id} not found")
            return None

        all_departments = [
            child_department
        ] + child_department.get_all_child_departments()
        staff_in_department = models.Staff.objects.filter(
            department__in=all_departments
        )
        logger.debug(
            f"Found {staff_in_department.count()} staff members in child department ID {child_department_id}"
        )

        staff_data = {}
        for staff_member in staff_in_department:
            if staff_member.surname == "Нет фамилии":
                fio = staff_member.name
            else:
                fio = f"{staff_member.surname} {staff_member.name}"

            staff_data[staff_member.pin] = {
                "FIO": fio,
                "date_of_creation": staff_member.date_of_creation,
                "avatar": (staff_member.avatar.url if staff_member.avatar else None),
                "positions": [
                    position.name for position in staff_member.positions.all()
                ],
            }
            logger.debug(f"Processed staff member: {fio} (PIN: {staff_member.pin})")

        sorted_staff_data = dict(
            sorted(staff_data.items(), key=lambda item: item[1]["FIO"])
        )
        logger.info(f"Sorted staff data for child department ID {child_department_id}")

        return {
            "child_department": serializers.ChildDepartmentSerializer(
                child_department
            ).data,
            "staff_count": staff_in_department.count(),
            "staff_data": sorted_staff_data,
        }

    try:
        data = get_cache(
            cache_key,
            query=fetch_child_department_data,
            timeout=10 * 60,
        )

        if data is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        logger.info(
            f"Returning detailed data for child department ID {child_department_id}"
        )
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in child_department_detail: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить информацию о сотруднике",
    operation_description="Получение подробной информации о сотруднике, включая данные о посещаемости, заработной плате и типе контракта.",
    tags=["Staff"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            name="staff_pin",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_STRING,
            required=True,
            description="Уникальный идентификатор сотрудника (PIN)",
        ),
        openapi.Parameter(
            name="start_date",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=False,
            description="Дата начала периода для фильтрации данных о посещаемости (формат: YYYY-MM-DD)",
        ),
        openapi.Parameter(
            name="end_date",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=False,
            description="Дата окончания периода для фильтрации данных о посещаемости (формат: YYYY-MM-DD)",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Данные сотрудника успешно получены",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "name": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Имя сотрудника",
                    ),
                    "surname": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Фамилия сотрудника",
                    ),
                    "positions": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                        description="Список должностей сотрудника",
                    ),
                    "avatar": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        format=openapi.FORMAT_URI,
                        nullable=True,
                        description="URL аватара сотрудника",
                    ),
                    "department": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Отдел, к которому относится сотрудник",
                    ),
                    "department_id": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        description="Id отдела",
                    ),
                    "attendance": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        description="Данные о посещаемости по датам. Ключ - дата в формате DD-MM-YYYY",
                        additional_properties=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="Данные о посещаемости за конкретную дату",
                            properties={
                                "first_in": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATETIME,
                                    nullable=True,
                                    description="Время первого входа в формате ISO 8601",
                                ),
                                "last_out": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATETIME,
                                    nullable=True,
                                    description="Время последнего выхода в формате ISO 8601",
                                ),
                                "area_name_in": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    nullable=True,
                                    description="Название места первого входа",
                                ),
                                "area_name_out": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    nullable=True,
                                    description=(
                                        "Название места последнего выхода. "
                                        "Примечание: если значение равно 'Unknown', рекомендуется парсить его как null."
                                    ),
                                ),
                                "first_in_source": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    nullable=True,
                                    description="Источник данных о первом входе (staff_attendance или lesson_attendance)",
                                ),
                                "last_out_source": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    nullable=True,
                                    description="Источник данных о последнем выходе (staff_attendance или lesson_attendance)",
                                ),
                                "percent_day": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format=openapi.FORMAT_FLOAT,
                                    description="Процент отработанного времени за день",
                                ),
                                "total_minutes": openapi.Schema(
                                    type=openapi.TYPE_NUMBER,
                                    format=openapi.FORMAT_FLOAT,
                                    description="Общее количество отработанных минут за день",
                                ),
                                "is_weekend": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN,
                                    description="Является ли день выходным",
                                ),
                                "is_remote_work": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN,
                                    description="Является ли работа удаленной",
                                ),
                                "is_absent_approved": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN,
                                    description="Утверждено ли отсутствие",
                                ),
                                "absent_reason": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    nullable=True,
                                    description="Причина отсутствия (если применимо)",
                                ),
                            },
                        ),
                    ),
                    "percent_for_period": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        format=openapi.FORMAT_FLOAT,
                        description="Общий процент работы за указанный период",
                    ),
                    "salary": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        format=openapi.FORMAT_FLOAT,
                        nullable=True,
                        description="Общая заработная плата сотрудника",
                    ),
                    "contract_type": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Тип контракта сотрудника",
                    ),
                    "bonus_percentage": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        description="Процент бонуса сотрудника",
                    ),
                },
            ),
        ),
        400: "Неверный запрос, дата начала не может быть позже даты окончания",
        404: "Сотрудник не найден",
    },
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def staff_detail(request, staff_pin):
    """
    **Получить информацию о сотруднике**

    Данный метод возвращает подробную информацию о сотруднике, включая данные о посещаемости, заработной плате и типе контракта за указанный период.

    ### Args:
        - **request (HttpRequest)**: Запрос, содержащий параметры запроса.
        - **staff_pin (str)**: Уникальный идентификатор сотрудника (PIN).

    ### Returns:
        - **Response**: Ответ с данными сотрудника или сообщением об ошибке.

    ### Raises:
        - **ValueError**: Если start_date больше end_date.
    """

    logger.info(f"Request received for staff details with PIN {staff_pin}")

    staff = get_cache(
        f"staff_{staff_pin}",
        query=lambda: fetch_staff_data(staff_pin),
        timeout=10 * 60,
    )

    if staff is None:
        logger.warning(f"Staff with PIN {staff_pin} not found")
        return Response(status=status.HTTP_404_NOT_FOUND)

    start_date, end_date = get_date_range(request)
    logger.debug(f"Retrieved date range: start_date={start_date}, end_date={end_date}")

    if start_date > end_date:
        logger.warning(
            f"Invalid date range: start_date {start_date} is greater than end_date {end_date}"
        )
        return Response(
            data={"error": "start_date cannot be greater than end_date"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cache_key = f"staff_detail_{staff_pin}_{start_date}_{end_date}"
    logger.debug(f"Generated cache key: {cache_key}")

    data = get_cache(
        cache_key,
        query=lambda: get_staff_detail(staff, start_date, end_date),
        timeout=30,
    )

    logger.info(f"Returning staff details for PIN {staff_pin}")
    return Response(data, status=status.HTTP_200_OK)


def fetch_staff_data(staff_pin):
    """Получение данных о сотруднике из базы данных.
    Args:
        staff_pin (str): Уникальный идентификатор сотрудника (PIN).
    Returns:
        models.Staff: Объект сотрудника.
        None: Если сотрудник не найден.
    """
    try:
        return models.Staff.objects.get(pin=staff_pin)
    except models.Staff.DoesNotExist:
        return None


def get_date_range(request):
    """
    Получение диапазона дат из параметров запроса.

    Если даты не указаны, используется период последних 7 дней.

    Args:
        request (HttpRequest): Запрос с параметрами.

    Returns:
        tuple: Кортеж с датами начала и окончания периода (datetime.date).
    """
    end_date_str = request.query_params.get(
        "end_date", timezone.now().strftime("%Y-%m-%d")
    )
    start_date_str = request.query_params.get(
        "start_date", (timezone.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    )

    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()

    return start_date, end_date


def get_staff_detail(staff, start_date, end_date):
    """
    Получение подробной информации о сотруднике за указанный период.

    Включает данные о посещаемости, процент присутствия, заработную плату и тип контракта.

    Args:
        staff (Staff): Объект сотрудника.
        start_date (datetime.date): Дата начала периода.
        end_date (datetime.date): Дата окончания периода.

    Returns:
        dict: Словарь с данными сотрудника.
    """
    logger.info(f"Получение деталей сотрудника {staff.name} (PIN: {staff.pin})")
    logger.debug(f"Запрошенный диапазон дат: {start_date} до {end_date}")

    attendance_qs = models.StaffAttendance.objects.filter(
        staff=staff,
        date_at__range=[
            start_date + datetime.timedelta(days=1),
            end_date + datetime.timedelta(days=1),
        ],
    )

    lesson_qs = models.LessonAttendance.objects.filter(
        staff=staff,
        date_at__range=[start_date, end_date],
    )

    location_cache = get_class_location_cache()
    kd_tree = location_cache["kd_tree"]
    class_names = location_cache["class_names"]
    if kd_tree and class_names:
        logger.debug(f"KDTree initialized with {len(class_names)} locations")

    combined_attendance = {}

    for record in attendance_qs:
        date_key = record.date_at - datetime.timedelta(days=1)
        if date_key not in combined_attendance:
            combined_attendance[date_key] = {
                "first_in": record.first_in,
                "last_out": record.last_out,
                "area_name_in": None,
                "area_name_out": None,
                "first_in_source": None,
                "last_out_source": None,
            }
            if record.area_name_in:
                area_address = utils.resolve_area_address(record.area_name_in)
                combined_attendance[date_key]["area_name_in"] = (
                    area_address or record.area_name_in
                )
            if record.area_name_out:
                area_address = utils.resolve_area_address(record.area_name_out)
                combined_attendance[date_key]["area_name_out"] = (
                    area_address or record.area_name_out
                )
            if record.first_in:
                combined_attendance[date_key]["first_in_source"] = "staff_attendance"
            if record.last_out:
                combined_attendance[date_key]["last_out_source"] = "staff_attendance"
        else:
            if record.first_in:
                current_first_in = combined_attendance[date_key]["first_in"]
                if not current_first_in or record.first_in < current_first_in:
                    combined_attendance[date_key]["first_in"] = record.first_in
                    combined_attendance[date_key][
                        "first_in_source"
                    ] = "staff_attendance"
                    if record.area_name_in:
                        area_address = utils.resolve_area_address(record.area_name_in)
                        combined_attendance[date_key]["area_name_in"] = (
                            area_address or record.area_name_in
                        )

            if record.last_out:
                current_last_out = combined_attendance[date_key]["last_out"]
                if not current_last_out or record.last_out > current_last_out:
                    combined_attendance[date_key]["last_out"] = record.last_out
                    combined_attendance[date_key][
                        "last_out_source"
                    ] = "staff_attendance"
                    if record.area_name_out:
                        area_address = utils.resolve_area_address(record.area_name_out)
                        combined_attendance[date_key]["area_name_out"] = (
                            area_address or record.area_name_out
                        )

    lesson_by_date = defaultdict(list)
    for record in lesson_qs:
        date_key = record.date_at
        lesson_by_date[date_key].append(record)

    for date_key, lesson_records in lesson_by_date.items():
        earliest_record = None
        latest_record = None

        for record in lesson_records:
            if record.first_in:
                if (
                    earliest_record is None
                    or record.first_in < earliest_record.first_in
                ):
                    earliest_record = record
            if record.last_out:
                if latest_record is None or record.last_out > latest_record.last_out:
                    latest_record = record

        if date_key not in combined_attendance:
            combined_attendance[date_key] = {
                "first_in": earliest_record.first_in if earliest_record else None,
                "last_out": latest_record.last_out if latest_record else None,
                "area_name_in": None,
                "area_name_out": None,
                "first_in_source": "lesson_attendance" if earliest_record else None,
                "last_out_source": "lesson_attendance" if latest_record else None,
            }
            if kd_tree and class_names:
                if earliest_record and earliest_record.first_in:
                    try:
                        _distances, indices = kd_tree.query(
                            [[earliest_record.latitude, earliest_record.longitude]], k=1
                        )
                        if hasattr(indices, "ndim") and indices.ndim > 1:
                            indices = indices.flatten()
                        if len(indices) > 0:
                            location_name = class_names[int(indices[0])]
                            combined_attendance[date_key][
                                "area_name_in"
                            ] = location_name
                    except Exception as e:
                        logger.warning(
                            f"Error finding location for earliest_record: {e}"
                        )
                if latest_record and latest_record.last_out:
                    try:
                        _distances, indices = kd_tree.query(
                            [[latest_record.latitude, latest_record.longitude]], k=1
                        )
                        if hasattr(indices, "ndim") and indices.ndim > 1:
                            indices = indices.flatten()
                        if len(indices) > 0:
                            location_name = class_names[int(indices[0])]
                            combined_attendance[date_key][
                                "area_name_out"
                            ] = location_name
                    except Exception as e:
                        logger.warning(f"Error finding location for latest_record: {e}")
        else:
            if earliest_record and earliest_record.first_in:
                current_first_in = combined_attendance[date_key]["first_in"]
                if not current_first_in or earliest_record.first_in < current_first_in:
                    combined_attendance[date_key]["first_in"] = earliest_record.first_in
                    combined_attendance[date_key][
                        "first_in_source"
                    ] = "lesson_attendance"
                    if kd_tree and class_names:
                        try:
                            _distances, indices = kd_tree.query(
                                [[earliest_record.latitude, earliest_record.longitude]],
                                k=1,
                            )
                            if hasattr(indices, "ndim") and indices.ndim > 1:
                                indices = indices.flatten()
                            if len(indices) > 0:
                                location_name = class_names[int(indices[0])]
                                combined_attendance[date_key][
                                    "area_name_in"
                                ] = location_name
                        except Exception as e:
                            logger.warning(
                                f"Error finding location for earliest_record: {e}"
                            )

            if latest_record and latest_record.last_out:
                current_last_out = combined_attendance[date_key]["last_out"]
                if not current_last_out or latest_record.last_out > current_last_out:
                    combined_attendance[date_key]["last_out"] = latest_record.last_out
                    combined_attendance[date_key][
                        "last_out_source"
                    ] = "lesson_attendance"
                    if kd_tree and class_names:
                        try:
                            _distances, indices = kd_tree.query(
                                [[latest_record.latitude, latest_record.longitude]], k=1
                            )
                            if hasattr(indices, "ndim") and indices.ndim > 1:
                                indices = indices.flatten()
                            if len(indices) > 0:
                                location_name = class_names[int(indices[0])]
                                combined_attendance[date_key][
                                    "area_name_out"
                                ] = location_name
                        except Exception as e:
                            logger.warning(
                                f"Error finding location for latest_record: {e}"
                            )

    logger.debug(f"Объединенные данные посещаемости: {combined_attendance}")

    holidays = models.PublicHoliday.objects.filter(
        date__range=[start_date, end_date]
    ).values_list("date", "is_working_day")
    logger.debug(f"Государственные праздники в периоде: {len(holidays)}")

    holiday_dict = dict(holidays)
    attendance_data = {}
    total_minutes_for_period = 0
    total_days_with_data = 0
    percent_for_period = 0

    remote_work_qs = models.RemoteWork.objects.filter(staff=staff).filter(
        Q(permanent_remote=True) | Q(start_date__lte=end_date, end_date__gte=start_date)
    )
    logger.debug(f"Получено периодов дистанционной работы: {remote_work_qs.count()}")

    absent_reason_qs = models.AbsentReason.objects.filter(
        staff=staff, start_date__lte=end_date, end_date__gte=start_date
    )
    logger.debug(f"Получено причин отсутствия: {absent_reason_qs.count()}")

    dates = []

    if attendance_qs.exists():
        attendance_dates = [
            attendance.date_at - datetime.timedelta(days=1)
            for attendance in attendance_qs
        ]
        dates.extend(attendance_dates)
    else:
        attendance_dates = []

    if lesson_qs.exists():
        lesson_dates = [lesson.date_at for lesson in lesson_qs]
        dates.extend(lesson_dates)

    if remote_work_qs.exists():
        remote_dates = []
        for remote_work in remote_work_qs:
            if remote_work.permanent_remote:
                remote_dates.extend(attendance_dates)
            else:
                rw_start = (
                    remote_work.start_date
                    if remote_work.start_date is not None
                    else start_date
                )
                rw_end = (
                    remote_work.end_date
                    if remote_work.end_date is not None
                    else end_date
                )
                remote_start = max(rw_start, start_date)
                remote_end = min(rw_end, end_date)
                if remote_start <= remote_end:
                    remote_dates.extend(
                        [
                            remote_start + datetime.timedelta(days=x)
                            for x in range((remote_end - remote_start).days + 1)
                        ]
                    )
        dates.extend(remote_dates)
    else:
        remote_dates = []

    if absent_reason_qs.exists():
        absent_dates = []
        for absent_reason in absent_reason_qs:
            absent_start = max(absent_reason.start_date, start_date)
            absent_end = min(absent_reason.end_date, end_date)
            absent_dates.extend(
                [
                    absent_start + datetime.timedelta(days=x)
                    for x in range((absent_end - absent_start).days + 1)
                ]
            )
        dates.extend(absent_dates)
    else:
        absent_dates = []

    if not dates:
        logger.warning(
            "Нет данных о посещаемости, дистанционной работе или причинах отсутствия за указанный период."
        )
        staff_detail_data = {
            "name": staff.name,
            "surname": staff.surname if staff.surname != "Нет фамилии" else "",
            "positions": [position.name for position in staff.positions.all()],
            "avatar": (
                staff.avatar.url if staff.avatar else "/media/images/no-avatar.png"
            ),
            "department": staff.department.name if staff.department else "N/A",
            "department_id": staff.department.id if staff.department else "N/A",
            "attendance": {},
            "percent_for_period": 0.0,
            "contract_type": None,
            "salary": None,
        }
        return staff_detail_data

    min_date = max(min(dates), start_date)
    max_date = min(max(dates), end_date)
    logger.debug(f"Фактический диапазон дат с данными: {min_date} до {max_date}")

    start_date = min_date
    end_date = max_date

    date_set = set(dates)
    logger.debug(f"Общее количество уникальных дат с данными: {len(date_set)}")

    num_days = len(date_set)
    cost_per_day = 100 / num_days
    logger.debug(
        f"Количество дней с данными: {num_days}, стоимость дня: {cost_per_day}"
    )

    average_attendance = get_average_attendance_for_period(staff, start_date, end_date)
    logger.debug(f"Средняя посещаемость за период: {average_attendance}%")

    K_adj = 1.25

    if average_attendance <= 0:
        logger.error(
            f"Критическая ошибка: средняя посещаемость равна нулю или отрицательна ({average_attendance}). "
            f"Используется дефолтное значение 85.0% для расчета штрафного коэффициента."
        )
        average_attendance = 85.0

    penalty_rate = (100 / average_attendance) * K_adj
    logger.debug(
        f"Расчет штрафного коэффициента: penalty_rate = (100 / {average_attendance}) * {K_adj} = {penalty_rate:.4f}"
    )

    salary_qs = models.Salary.objects.filter(staff=staff).first()
    contract_type = salary_qs.contract_type if salary_qs else "full_time"
    total_minutes_expected_per_day = get_expected_minutes_per_day(contract_type)
    logger.debug(
        f"Тип контракта: {contract_type}, ожидаемые минуты в день: {total_minutes_expected_per_day}"
    )

    for event_date in sorted(date_set):
        logger.debug(f"Обработка даты: {event_date}")

        attendance = combined_attendance.get(event_date)
        (
            attendance_record,
            total_minutes_for_period,
            total_days_with_data,
            percent_for_period,
        ) = process_attendance(
            attendance,
            event_date,
            start_date,
            end_date,
            holiday_dict,
            total_minutes_expected_per_day,
            cost_per_day,
            penalty_rate,
            total_minutes_for_period,
            total_days_with_data,
            percent_for_period,
            remote_work_qs,
            absent_reason_qs,
        )

        if attendance_record:
            attendance_data[event_date.strftime("%d-%m-%Y")] = attendance_record
            logger.debug(
                f"Добавлена запись посещаемости для {event_date}: {attendance_record}"
            )

    if total_days_with_data > 0:
        percent_for_period /= total_days_with_data
        percent_for_period = max(percent_for_period, 0)
        logger.debug(f"Итоговый процент за период: {percent_for_period}")
    else:
        percent_for_period = 0.0
        logger.debug("Нет рабочих дней для расчета процента за период.")

    num_days = len(date_set)
    bonus_percentage = utils.get_bonus_percentage(num_days, percent_for_period)
    logger.info(
        f"Рассчитанный бонус: {bonus_percentage}% для {num_days} дней и {percent_for_period}% присутствия."
    )

    avatar_url = staff.avatar.url if staff.avatar else "/media/images/no-avatar.png"
    logger.debug(f"URL аватара: {avatar_url}")

    staff_detail_payload = {
        "name": staff.name,
        "surname": staff.surname if staff.surname != "Нет фамилии" else "",
        "positions": [position.name for position in staff.positions.all()],
        "avatar": avatar_url,
        "department": staff.department.name if staff.department else "N/A",
        "department_id": staff.department.id if staff.department else "N/A",
        "attendance": attendance_data,
        "percent_for_period": round(percent_for_period, 2),
        "bonus_percentage": bonus_percentage,
        "contract_type": salary_qs.contract_type if salary_qs else None,
        "salary": salary_qs.total_salary if salary_qs else None,
    }

    logger.info(
        f"Генерация деталей сотрудника завершена для {staff.name} (PIN: {staff.pin})"
    )
    return staff_detail_payload


def get_average_attendance_for_period(staff, start_date, end_date):
    """
    Расчет среднего процента присутствия за предыдущий аналогичный период.

    Args:
        staff (Staff): Объект сотрудника.
        start_date (datetime.date): Дата начала текущего периода.
        end_date (datetime.date): Дата окончания текущего периода.

    Returns:
        float: Средний процент присутствия за предыдущий период.
    """
    logger.info(
        f"Calculating average attendance for staff {staff.name} (PIN: {staff.pin}) from {start_date} to {end_date}"
    )

    previous_start_date = start_date - datetime.timedelta(days=30)
    previous_end_date = end_date - datetime.timedelta(days=30)
    logger.debug(f"Previous period range: {previous_start_date} to {previous_end_date}")

    previous_attendance_qs = models.StaffAttendance.objects.filter(
        staff=staff, date_at__range=[previous_start_date, previous_end_date]
    )
    logger.debug(
        f"Retrieved {previous_attendance_qs.count()} attendance records for previous period"
    )

    if not previous_attendance_qs.exists():
        logger.warning(
            "No attendance records found for the previous period. Returning default average attendance of 85.0%"
        )
        return 85.0

    total_minutes = 0
    total_days = 0

    for attendance in previous_attendance_qs:
        first_in = attendance.first_in
        last_out = attendance.last_out

        if first_in and last_out:
            minutes_present = (last_out - first_in).total_seconds() / 60
            if minutes_present > 0:
                total_minutes += minutes_present
                total_days += 1
                logger.debug(
                    f"Processed attendance for {attendance.date_at}: {minutes_present} minutes present"
                )

    if total_days == 0:
        logger.warning(
            "No complete attendance days found for the previous period. Returning default average attendance of 85.0%"
        )
        return 85.0

    average_attendance = (total_minutes / (total_days * 8 * 60)) * 100

    if average_attendance <= 0:
        logger.warning(
            f"Calculated average attendance is {average_attendance}% (invalid). "
            f"Using default value of 85.0% for KPI calculation."
        )
        return 85.0

    if average_attendance < 1.0:
        logger.warning(
            f"Calculated average attendance is very low ({average_attendance}%). "
            f"Using minimum threshold of 1.0% for KPI calculation to prevent unrealistic penalties."
        )
        return 1.0

    logger.info(
        f"Calculated average attendance for previous period: {average_attendance}%"
    )
    return average_attendance


def get_expected_minutes_per_day(contract_type):
    """
    Получение ожидаемого количества рабочих минут в день на основе типа контракта.

    Args:
        contract_type (str): Тип контракта сотрудника.

    Returns:
        int: Ожидаемые минуты в день.
    """
    if contract_type in ["part_time", "gph"]:
        return 4 * 60
    return 8 * 60


def process_attendance(
    attendance,
    event_date,
    start_date,
    end_date,
    holiday_dict,
    total_minutes_expected_per_day,
    cost_per_day,
    penalty_rate,
    total_minutes_for_period,
    total_days_with_data,
    percent_for_period,
    remote_work_qs,
    absent_reason_qs,
):
    """
    Обработка данных о посещаемости для конкретной даты с учетом новых требований.

    Args:
        attendance (StaffAttendance): Запись о посещаемости за дату, если есть.
        event_date (datetime.date): Дата, которую обрабатываем.
        start_date (datetime.date): Дата начала периода.
        end_date (datetime.date): Дата окончания периода.
        holiday_dict (dict): Словарь с информацией о праздничных днях.
        total_minutes_expected_per_day (int): Ожидаемое количество минут работы в день.
        cost_per_day (float): Стоимость одного дня в процентах.
        penalty_rate (float): Штрафной коэффициент за отсутствие.
        total_minutes_for_period (float): Общее количество минут за период.
        total_days_with_data (int): Общее количество дней с данными.
        percent_for_period (float): Процент рабочего времени за период.
        remote_work_qs (QuerySet): QuerySet с периодами дистанционной работы сотрудника.
        absent_reason_qs (QuerySet): QuerySet с причинами отсутствия сотрудника.

    Returns:
        tuple: Кортеж, содержащий:
            - attendance_record (dict): Обработанные данные о посещаемости за дату.
            - total_minutes_for_period (float): Обновленное общее количество минут за период.
            - total_days_with_data (int): Обновленное количество дней с данными.
            - percent_for_period (float): Обновленный процент рабочего времени за период.
    """
    logger.info(f"Обработка посещаемости за дату {event_date}")

    if not (start_date <= event_date <= end_date):
        logger.warning(
            f"Дата события {event_date} вне указанного диапазона {start_date} до {end_date}"
        )
        return None, total_minutes_for_period, total_days_with_data, percent_for_period

    is_off_day = check_off_day(event_date, holiday_dict)
    logger.debug(f"Является ли выходным днем: {is_off_day} для даты {event_date}")

    absent_reason = absent_reason_qs.filter(
        start_date__lte=event_date, end_date__gte=event_date
    ).first()

    first_in = attendance.get("first_in") if attendance else None
    last_out = attendance.get("last_out") if attendance else None
    area_name_in = attendance.get("area_name_in") if attendance else None
    area_name_out = attendance.get("area_name_out") if attendance else None

    if is_off_day:
        if first_in and last_out:
            total_minutes_worked = calculate_effective_minutes_with_lunch(
                first_in, last_out
            )
            percent_day = (total_minutes_worked / total_minutes_expected_per_day) * 100
            logger.info(
                f"Сотрудник работал в выходной день {event_date}. Данные отображаются, но не влияют на расчеты."
            )
        else:
            total_minutes_worked = 0
            percent_day = 0
            logger.info(
                f"Выходной день {event_date} без данных о посещаемости. Пропускаем."
            )

        attendance_record = {
            "first_in": (
                first_in.astimezone(timezone.get_current_timezone())
                if first_in
                else None
            ),
            "last_out": (
                last_out.astimezone(timezone.get_current_timezone())
                if last_out
                else None
            ),
            "area_name_in": area_name_in,
            "area_name_out": area_name_out,
            "percent_day": round(percent_day, 2),
            "total_minutes": round(total_minutes_worked, 2),
            "is_weekend": True,
            "is_remote_work": False,
            "is_absent_approved": False,
            "absent_reason": None,
        }
        return (
            attendance_record,
            total_minutes_for_period,
            total_days_with_data,
            percent_for_period,
        )

    is_remote_work = remote_work_qs.filter(
        Q(permanent_remote=True)
        | Q(start_date__lte=event_date, end_date__gte=event_date)
    ).exists()

    is_absent_approved = False
    absent_reason_display = None

    if is_remote_work:
        percent_day = 100.0
        total_minutes_worked = total_minutes_expected_per_day
        total_minutes_for_period += total_minutes_worked
        total_days_with_data += 1
        percent_for_period += percent_day
        logger.info(f"{event_date} отмечен как день дистанционной работы.")
    elif absent_reason:
        is_absent_approved = absent_reason.approved
        absent_reason_display = absent_reason.get_reason_display()
        if is_absent_approved:
            logger.info(
                f"{event_date} утвержденная причина отсутствия: {absent_reason_display}."
            )
            attendance_record = {
                "first_in": (
                    first_in.astimezone(timezone.get_current_timezone())
                    if first_in
                    else None
                ),
                "last_out": (
                    last_out.astimezone(timezone.get_current_timezone())
                    if last_out
                    else None
                ),
                "area_name_in": area_name_in,
                "area_name_out": area_name_out,
                "percent_day": 0,
                "total_minutes": 0,
                "is_weekend": False,
                "is_remote_work": False,
                "is_absent_approved": True,
                "absent_reason": absent_reason_display,
            }
            return (
                attendance_record,
                total_minutes_for_period,
                total_days_with_data,
                percent_for_period,
            )
        else:
            percent_day = 0
            total_minutes_worked = 0
            total_days_with_data += 1
            penalty = penalty_rate * cost_per_day
            percent_for_period -= penalty
            logger.warning(
                f"{event_date} неутвержденная причина отсутствия: {absent_reason_display}. Применяется штраф {penalty}%."
            )
    else:
        if first_in and last_out:
            total_minutes_worked = calculate_effective_minutes_with_lunch(
                first_in, last_out
            )
            percent_day = (total_minutes_worked / total_minutes_expected_per_day) * 100
            total_minutes_for_period += total_minutes_worked
            total_days_with_data += 1
            percent_for_period += percent_day
            logger.debug(
                f"Отработано минут: {total_minutes_worked}, Процент дня: {percent_day}"
            )
        else:
            percent_day = 0
            total_minutes_worked = 0
            total_days_with_data += 1
            penalty = penalty_rate * cost_per_day
            percent_for_period -= penalty
            logger.warning(
                f"Нет записей о посещаемости за дату {event_date}. Применяется штраф {penalty}%. "
            )

    attendance_record = {
        "first_in": (
            first_in.astimezone(timezone.get_current_timezone()) if first_in else None
        ),
        "last_out": (
            last_out.astimezone(timezone.get_current_timezone()) if last_out else None
        ),
        "area_name_in": area_name_in,
        "area_name_out": area_name_out,
        "percent_day": round(percent_day, 2),
        "total_minutes": round(total_minutes_worked, 2),
        "is_weekend": is_off_day,
        "is_remote_work": is_remote_work,
        "is_absent_approved": is_absent_approved,
        "absent_reason": absent_reason_display,
    }
    logger.info(
        f"Обработана запись посещаемости за дату {event_date}: {attendance_record}"
    )

    return (
        attendance_record,
        total_minutes_for_period,
        total_days_with_data,
        percent_for_period,
    )


def check_off_day(event_date, holiday_dict):
    """
    Проверка, является ли дата выходным или праздничным днем.

    Args:
        event_date (datetime.date): Дата для проверки.
        holiday_dict (dict): Словарь с информацией о праздничных днях.

    Returns:
        bool: True, если день является выходным или праздничным, иначе False.
    """
    is_weekend = event_date.weekday() >= 5
    is_holiday = event_date in holiday_dict
    return (is_weekend and event_date not in holiday_dict) or (
        is_holiday and not holiday_dict[event_date]
    )


def update_percent_for_period(
    percent_for_period,
    percent_day,
    is_off_day,
    total_minutes_worked,
    cost_per_day,
    penalty_rate,
):
    """
    Обновление накопленного процента за период на основе ежедневной посещаемости.

    Args:
        percent_for_period (float): Текущий накопленный процент.
        percent_day (float): Процент присутствия за день.
        is_off_day (bool): Является ли день выходным.
        total_minutes_worked (float): Отработано минут за день.
        cost_per_day (float): Стоимость одного дня в процентах.
        penalty_rate (float): Штрафной коэффициент за отсутствие.

    Returns:
        float: Обновленный процент за период.
    """
    logger.debug(
        f"Updating percent for period. Initial: {percent_for_period}%, "
        f"Day percent: {percent_day}%, Is off day: {is_off_day}, "
        f"Total minutes worked: {total_minutes_worked}, "
        f"Cost per day: {cost_per_day}%, Penalty rate: {penalty_rate}%"
    )

    if is_off_day and total_minutes_worked > 0:
        percent_for_period += percent_day * 1.5
        logger.info(f"Off day with work. Increasing percent by {percent_day * 1.5}%.")
    elif not is_off_day and total_minutes_worked == 0:
        penalty = penalty_rate * cost_per_day
        percent_for_period -= penalty
        logger.warning(f"Workday with no work. Decreasing percent by {penalty}%.")
    else:
        percent_for_period += percent_day
        logger.info(f"Regular day. Adding {percent_day}% to the period percent.")

    logger.debug(f"Updated percent for period: {percent_for_period}%")
    return percent_for_period


@swagger_auto_schema(
    method="get",
    operation_summary="Проверка статуса задачи создания записей посещаемости",
    operation_description=(
        "Проверяет статус задачи, созданной POST /api/lesson_attendance/ (task_id из ответа 202). "
        "Возвращает: Pending (202) — задача в очереди; Success (200) — lesson_ids созданных записей; "
        "Failure (500) — error с текстом ошибки. Остальные состояния — 200 с полем status."
    ),
    tags=["Lesson Attendance"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            "task_id",
            openapi.IN_PATH,
            description="ID задачи, полученный при создании записей посещаемости",
            type=openapi.TYPE_STRING,
            required=True,
        ),
    ],
    responses={
        200: openapi.Response(
            description="Задача выполнена успешно или в процессе выполнения",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Статус задачи (Success, Pending, или другой)",
                    ),
                    "lesson_ids": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_INTEGER),
                        description="Список ID созданных записей посещаемости (только при Success)",
                    ),
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение о статусе задачи",
                    ),
                },
            ),
        ),
        202: openapi.Response(
            description="Задача в очереди, ожидает выполнения",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Статус задачи (Pending)",
                    ),
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение о том, что задача в очереди",
                    ),
                },
            ),
        ),
        500: openapi.Response(
            description="Ошибка при выполнении задачи или проверке статуса",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Статус задачи (Failure)",
                    ),
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Описание ошибки",
                    ),
                },
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def check_lesson_task_status(request, task_id):
    """
    Проверка статуса задачи и получение lesson_id.
    """
    log_prefix = "[lesson_attendance]"
    ip_address = request.META.get("REMOTE_ADDR", "Неизвестный IP")

    try:
        task_result = AsyncResult(task_id)

        if task_result.state == "PENDING":
            lesson_attendance_logger.debug(
                "%s task_status PENDING task_id=%s ip=%s",
                log_prefix,
                task_id,
                ip_address,
            )
            return Response(
                {
                    "status": "Pending",
                    "message": "Задача в очереди, ожидайте завершения",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        elif task_result.state == "SUCCESS":
            result = task_result.result or {}
            success_records = result.get("success_records", [])
            error_records = result.get("error_records", [])
            lesson_attendance_logger.info(
                "%s task_status SUCCESS task_id=%s ip=%s created=%s failed=%s",
                log_prefix,
                task_id,
                ip_address,
                len(success_records),
                len(error_records),
            )
            if error_records:
                lesson_attendance_logger.warning(
                    "%s task_status partial_failures task_id=%s error_records=%s",
                    log_prefix,
                    task_id,
                    error_records,
                )
            return Response(
                {"status": "Success", "lesson_ids": success_records},
                status=status.HTTP_200_OK,
            )

        elif task_result.state == "FAILURE":
            lesson_attendance_logger.warning(
                "%s task_status FAILURE task_id=%s ip=%s error=%s",
                log_prefix,
                task_id,
                ip_address,
                str(task_result.info),
            )
            return Response(
                {"status": "Failure", "error": str(task_result.info)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        else:
            lesson_attendance_logger.info(
                "%s task_status state=%s task_id=%s ip=%s",
                log_prefix,
                task_result.state,
                task_id,
                ip_address,
            )
            return Response(
                {
                    "status": task_result.state,
                    "message": "Задача в процессе выполнения",
                },
                status=status.HTTP_200_OK,
            )

    except Exception as e:
        lesson_attendance_logger.exception(
            "%s task_status EXCEPTION task_id=%s ip=%s error=%s",
            log_prefix,
            task_id,
            ip_address,
            str(e),
        )
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _lesson_attendance_responses():
    """Общие ответы для создания записей посещаемости (multipart и JSON)."""
    return {
        202: openapi.Response(
            description="Задача принята в очередь. Идентификатор задачи — в task_id.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                    "task_id": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Проверка: GET /api/lesson_attendance/task_status/{task_id}/",
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description="Ошибка валидации.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                    "missing": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                },
            ),
        ),
        500: openapi.Response(
            description="Ошибка сервера.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
            ),
        ),
    }


@swagger_auto_schema(
    method="post",
    auto_schema=FormOnlySwaggerAutoSchema,  # type: ignore[reportArgumentType]
    operation_summary="Создание записей посещаемости (multipart/form-data)",
    operation_description=(
        "**Как заполнять запрос**\n\n"
        "1. В поле **attendance_data** вставьте одну строку — JSON-массив с записями посещаемости. "
        "Одна запись — один объект с полями ниже. Несколько записей — несколько объектов в массиве.\n\n"
        "2. В поле **image** нажмите «Choose File» и выберите файл фотографии (JPG или PNG).\n\n"
        "**Формат одной записи в attendance_data** (все поля обязательны, кроме subject_name):\n"
        "- **staff_pin** (строка) — PIN сотрудника из справочника, например `s00260s`\n"
        "- **tutor_id** (число) — ID преподавателя, можно 0\n"
        "- **tutor** (строка) — ФИО преподавателя, например `Иванов И.И.`\n"
        "- **first_in** (строка) — дата и время начала занятия в формате ISO 8601 с таймзоной, например `2024-10-06T14:24:24+05:00`\n"
        "- **latitude** (число) — широта, можно 0\n"
        "- **longitude** (число) — долгота, можно 0\n"
        "- **subject_name** (строка, необязательно) — название предмета\n\n"
        "**Пример значения для attendance_data** (скопируйте и при необходимости отредактируйте):\n"
        "```\n"
        '[{"staff_pin":"s00260s","tutor_id":1,"tutor":"Иванов И.И.",'
        '"first_in":"2024-10-06T14:24:24+05:00","latitude":43.21,"longitude":76.85,"subject_name":"Математика"}]\n'
        "```\n\n"
        "**Ответ:** 202 Accepted, в теле — `task_id`. Результат создания записей смотрите в **GET** `/api/lesson_attendance/task_status/{task_id}/`.\n\n"
        "Вариант с JSON в теле и фото в Base64: **POST** `/api/lesson_attendance/json/`."
    ),
    tags=["Lesson Attendance"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API-ключ (альтернатива JWT).",
        ),
        openapi.Parameter(
            name="attendance_data",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            required=True,
            description="Строка JSON: массив объектов. В каждом объекте: staff_pin, tutor_id, tutor, first_in, latitude, longitude; по желанию subject_name. Пример см. в описании операции.",
        ),
        openapi.Parameter(
            name="image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Файл фотографии (JPG, PNG). Нажмите «Choose File» и выберите файл.",
        ),
    ],
    request_body=no_body,
    consumes=["multipart/form-data"],
    responses=_lesson_attendance_responses(),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def create_lesson_attendance(request):
    """
    POST /api/lesson_attendance/ — создание записей посещаемости занятий (с фото).

    Как заполнять запрос
    --------------------
    Поддерживаются два типа запроса.

    **1. multipart/form-data** (форма с файлом, в т.ч. в Swagger «Try it out»):
    - Поле **attendance_data**: строка, содержащая JSON-массив объектов. Каждый объект — одна запись посещаемости.
    - Поле **image**: файл изображения (JPG/PNG).

    Обязательные поля в каждом объекте массива attendance_data:
    - staff_pin (str): PIN сотрудника из справочника Staff.
    - tutor_id (int): ID преподавателя (допускается 0).
    - tutor (str): ФИО преподавателя.
    - first_in (str): Время начала занятия, ISO 8601 с таймзоной, напр. "2024-10-06T14:24:24+05:00".
    - latitude (float): Широта (допускается 0).
    - longitude (float): Долгота (допускается 0).

    Необязательное поле: subject_name (str).

    Пример значения для attendance_data (одна запись):
        [{"staff_pin":"s00260","tutor_id":1,"tutor":"Иванов И.И.","first_in":"2024-10-06T14:24:24+05:00","latitude":43.21,"longitude":76.85}]

    **2. application/json** (предпочтительно отправлять на POST /api/lesson_attendance/json/):
    - Тело: {"attendance_data": [ {...}, ... ], "image": "<base64-строка>"}.
    - Структура объектов в attendance_data — та же, image — фото в Base64 без префикса data:...

    Ответ
    -----
    - 202: в теле {"message": "Task accepted", "task_id": "<uuid>"}. Результат проверять в GET /api/lesson_attendance/task_status/<task_id>/.
    - 400: ошибка валидации (нет полей, неверный JSON, нет фото и т.п.).
    - 500: ошибка сервера при постановке задачи в очередь.
    """
    ip_address = request.META.get("REMOTE_ADDR", "Неизвестный IP")
    domain = request.get_host()
    log_prefix = "[lesson_attendance]"

    lesson_attendance_logger.info(
        "%s POST create ip=%s host=%s content_type=%s",
        log_prefix,
        ip_address,
        domain,
        getattr(request, "content_type", None),
    )

    try:
        ct = (getattr(request, "content_type") or "") or ""
        if "multipart" in ct or "form-data" in ct:
            attendance_data_raw = request.POST.get(
                "attendance_data"
            ) or request.data.get("attendance_data")
            image_base64 = request.POST.get("image") or request.data.get("image")
        else:
            attendance_data_raw = request.data.get("attendance_data")
            image_base64 = request.data.get("image")
        has_file = bool(request.FILES.get("image"))

        if not attendance_data_raw:
            _data_keys = (
                list(request.data.keys()) if getattr(request, "data", None) else []
            )
            _post_keys = list(request.POST.keys()) if hasattr(request, "POST") else []
            lesson_attendance_logger.warning(
                "%s BAD_REQUEST attendance_data_missing ip=%s data_keys=%s post_keys=%s",
                log_prefix,
                ip_address,
                _data_keys,
                _post_keys,
            )
            return Response(
                {"error": "Attendance data is missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(attendance_data_raw, list):
            attendance_data = attendance_data_raw
        elif isinstance(attendance_data_raw, (str, bytes)):
            attendance_data_raw = (
                attendance_data_raw.decode("utf-8")
                if isinstance(attendance_data_raw, bytes)
                else attendance_data_raw
            )
            try:
                attendance_data = json.loads(attendance_data_raw)
            except json.JSONDecodeError as e:
                lesson_attendance_logger.warning(
                    "%s BAD_REQUEST attendance_data_not_json ip=%s error=%s",
                    log_prefix,
                    ip_address,
                    str(e),
                )
                return Response(
                    {"error": "Invalid JSON in attendance_data"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            attendance_data = []

        if not isinstance(attendance_data, list):
            lesson_attendance_logger.warning(
                "%s BAD_REQUEST attendance_data_not_list ip=%s type=%s",
                log_prefix,
                ip_address,
                type(attendance_data).__name__,
            )
            return Response(
                {"error": "attendance_data must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def _missing_required(rec):
            missing = []
            if not rec.get("staff_pin"):
                missing.append("staff_pin")
            if "tutor_id" not in rec:
                missing.append("tutor_id")
            if not rec.get("tutor"):
                missing.append("tutor")
            if not rec.get("first_in"):
                missing.append("first_in")
            if "latitude" not in rec:
                missing.append("latitude")
            if "longitude" not in rec:
                missing.append("longitude")
            return missing

        for idx, record in enumerate(attendance_data):
            if not isinstance(record, dict):
                lesson_attendance_logger.warning(
                    "%s BAD_REQUEST record_not_dict ip=%s record_index=%s",
                    log_prefix,
                    ip_address,
                    idx,
                )
                return Response(
                    {"error": "Each attendance record must be an object"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            missing = _missing_required(record)
            if missing:
                lesson_attendance_logger.warning(
                    "%s BAD_REQUEST missing_required_fields ip=%s record_index=%s missing=%s staff_pin=%s tutor_id=%s",
                    log_prefix,
                    ip_address,
                    idx,
                    missing,
                    record.get("staff_pin"),
                    record.get("tutor_id"),
                )
                return Response(
                    {"error": "Missing required fields in record", "missing": missing},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        image_content = None
        image_name = None

        if has_file:
            staff_image = request.FILES["image"]
            image_content = staff_image.read()
        elif image_base64:
            try:
                image_content = base64.b64decode(image_base64)
            except Exception as e:
                lesson_attendance_logger.warning(
                    "%s BAD_REQUEST image_base64_decode_failed ip=%s error=%s",
                    log_prefix,
                    ip_address,
                    str(e),
                )
                return Response(
                    {"error": "Invalid Base64 image format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if not image_content:
            lesson_attendance_logger.warning(
                "%s BAD_REQUEST image_missing ip=%s records_count=%s (expected multipart image or JSON image base64)",
                log_prefix,
                ip_address,
                len(attendance_data),
            )
            return Response(
                {"error": "Image is missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = tasks.process_lesson_attendance_batch.apply_async(
            args=[attendance_data, image_name, image_content]
        )
        lesson_attendance_logger.info(
            "%s ACCEPTED task_id=%s ip=%s records_count=%s image_size_bytes=%s",
            log_prefix,
            task.id,
            ip_address,
            len(attendance_data),
            len(image_content),
        )

        return Response(
            {"message": "Task accepted", "task_id": task.id},
            status=status.HTTP_202_ACCEPTED,
        )

    except Exception as e:
        lesson_attendance_logger.exception(
            "%s EXCEPTION create ip=%s error=%s",
            log_prefix,
            ip_address,
            str(e),
        )
        return Response(
            {"error": "Error with creating job"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


_lesson_attendance_json_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=["attendance_data", "image"],
    description="Тело запроса: массив записей и фото в Base64.",
    properties={
        "attendance_data": openapi.Schema(
            type=openapi.TYPE_ARRAY,
            description="Массив записей посещаемости.",
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                required=[
                    "staff_pin",
                    "tutor_id",
                    "tutor",
                    "first_in",
                    "latitude",
                    "longitude",
                ],
                properties={
                    "staff_pin": openapi.Schema(
                        type=openapi.TYPE_STRING, example="s00260"
                    ),
                    "tutor_id": openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                    "tutor": openapi.Schema(
                        type=openapi.TYPE_STRING, example="Иванов И.И."
                    ),
                    "first_in": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        format=openapi.FORMAT_DATETIME,
                        example="2024-10-06T14:24:24+05:00",
                    ),
                    "latitude": openapi.Schema(
                        type=openapi.TYPE_NUMBER, example=43.207674
                    ),
                    "longitude": openapi.Schema(
                        type=openapi.TYPE_NUMBER, example=76.851377
                    ),
                    "subject_name": openapi.Schema(
                        type=openapi.TYPE_STRING, example="Математика"
                    ),
                },
            ),
        ),
        "image": openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Фото в Base64 (без префикса data:image/...;base64,).",
        ),
    },
)


@swagger_auto_schema(
    method="post",
    operation_summary="Создание записей посещаемости (application/json)",
    operation_description=(
        "Вариант с JSON в теле запроса и фото в Base64. Ответ 202 + task_id; "
        "результат: GET /api/lesson_attendance/task_status/{task_id}/.\n\n"
        'Тело: { "attendance_data": [ {...}, ... ], "image": "<base64>" }. '
        "Обязательные поля в каждой записи: staff_pin, tutor_id, tutor, first_in, latitude, longitude; "
        "опционально subject_name. Для загрузки файла используйте операцию **POST .../lesson_attendance/** (multipart) выше."
    ),
    tags=["Lesson Attendance"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API-ключ (альтернатива JWT).",
        ),
    ],
    request_body=_lesson_attendance_json_schema,
    consumes=["application/json"],
    responses=_lesson_attendance_responses(),
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def create_lesson_attendance_json(request):
    return create_lesson_attendance(request)


@swagger_auto_schema(
    method="put",
    operation_summary="Обновление записи посещаемости занятия",
    operation_description="Обновляет существующую запись посещаемости занятия по её ID. Параметр `last_out` обязателен, так как он указывает время окончания занятия. Параметры `first_in`, `latitude` и `longitude` могут быть обновлены опционально.",
    tags=["Lesson Attendance"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            "id",
            openapi.IN_PATH,
            description="ID записи для обновления",
            type=openapi.TYPE_INTEGER,
            required=True,
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["last_out"],
        properties={
            "first_in": openapi.Schema(
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATETIME,
                description="Время начала занятия в формате ISO 8601 с часовым поясом. Опционально",
                example="2024-09-16T17:28:24+05:00",
            ),
            "last_out": openapi.Schema(
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATETIME,
                description="Время окончания занятия в формате ISO 8601 с часовым поясом. Обязательно",
                example="2024-09-16T18:28:24+05:00",
            ),
            "latitude": openapi.Schema(
                type=openapi.TYPE_NUMBER,
                format=openapi.FORMAT_FLOAT,
                description="Широта места проведения. Опционально",
                example=43.222,
            ),
            "longitude": openapi.Schema(
                type=openapi.TYPE_NUMBER,
                format=openapi.FORMAT_FLOAT,
                description="Долгота места проведения. Опционально",
                example=76.851,
            ),
        },
    ),
    responses={
        200: openapi.Response(
            description="Запись успешно обновлена",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение об успешном обновлении записи",
                    ),
                    "lesson_id": openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description="ID обновленной записи посещаемости",
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description="Неверные данные или отсутствует обязательный параметр `last_out`",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
        404: openapi.Response(
            description="Запись с указанным ID не найдена",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
        500: openapi.Response(
            description="Ошибка сервера",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
    },
)
@api_view(["PUT"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def update_lesson_attendance(request, attendance_id):
    """
    Обновление записи посещаемости занятия.

    Args:
        id (int): ID записи для обновления.
        request (Request): HTTP запрос, содержащий данные для обновления записи.

    Ожидаемые параметры:
        last_out (str): Время окончания занятия в формате ISO 8601 с часовым поясом (обязательно).
        first_in (str): Время начала занятия в формате ISO 8601 с часовым поясом (опционально).
        latitude (float): Широта места проведения (опционально).
        longitude (float): Долгота места проведения (опционально).

    Returns:
        Response: Возвращает сообщение об успешном обновлении записи.
    """
    ip_address = request.META.get("REMOTE_ADDR", "Неизвестный IP")
    log_prefix = "[lesson_attendance]"

    try:
        lesson_attendance = get_object_or_404(models.LessonAttendance, id=attendance_id)

        first_in = request.data.get("first_in", lesson_attendance.first_in)
        last_out = request.data.get("last_out")
        latitude = request.data.get("latitude", lesson_attendance.latitude)
        longitude = request.data.get("longitude", lesson_attendance.longitude)

        if not last_out:
            lesson_attendance_logger.warning(
                "%s PUT BAD_REQUEST last_out_required id=%s ip=%s",
                log_prefix,
                attendance_id,
                ip_address,
            )
            return Response(
                {"error": "'last_out' is required for updating."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson_attendance.first_in = first_in
        lesson_attendance.last_out = last_out
        lesson_attendance.latitude = latitude
        lesson_attendance.longitude = longitude
        lesson_attendance.save()

        lesson_attendance_logger.info(
            "%s PUT OK lesson_id=%s ip=%s last_out=%s",
            log_prefix,
            lesson_attendance.id,
            ip_address,
            last_out,
        )
        return Response(
            {
                "message": "LessonAttendance updated successfully",
                "lesson_id": lesson_attendance.id,
            },
            status=status.HTTP_200_OK,
        )

    except models.LessonAttendance.DoesNotExist:
        lesson_attendance_logger.warning(
            "%s PUT NOT_FOUND id=%s ip=%s",
            log_prefix,
            attendance_id,
            ip_address,
        )
        return Response(
            {"error": "LessonAttendance not found."}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        lesson_attendance_logger.exception(
            "%s PUT EXCEPTION id=%s ip=%s error=%s",
            log_prefix,
            attendance_id,
            ip_address,
            str(e),
        )
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="get",
    operation_summary="Посещаемость сотрудников по отделу",
    operation_description="Получить данные о посещаемости сотрудников по ID подразделения и его дочерним подразделениям за указанный период.",
    tags=["Attendance & Statistics"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            "end_date",
            openapi.IN_QUERY,
            description="Конечная дата периода в формате YYYY-MM-DD",
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "start_date",
            openapi.IN_QUERY,
            description="Начальная дата периода в формате YYYY-MM-DD",
            type=openapi.TYPE_STRING,
            required=True,
        ),
        openapi.Parameter(
            "page",
            openapi.IN_QUERY,
            description="Номер страницы для пагинации",
            type=openapi.TYPE_INTEGER,
            required=False,
        ),
        openapi.Parameter(
            "page_size",
            openapi.IN_QUERY,
            description="Количество записей на странице (максимум 500)",
            type=openapi.TYPE_INTEGER,
            required=False,
        ),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def staff_detail_by_department_id(request, department_id):
    """
    Получить данные о посещаемости сотрудников по ID подразделения.

    Этот эндпоинт возвращает данные о посещаемости сотрудников для указанного подразделения и его дочерних подразделений за указанный период.

    Параметры запроса:
    - end_date: Конечная дата периода в формате YYYY-MM-DD.
    - start_date: Начальная дата периода в формате YYYY-MM-DD.
    - page: Номер страницы для пагинации (по умолчанию 1).
    - page_size: Количество записей на странице (максимум 500).

    Возвращаемые данные:
    - count: Общее количество записей.
    - next: URL следующей страницы результатов.
    - previous: URL предыдущей страницы результатов.
    - results: Список посещаемости сотрудников, сгруппированных по датам и по каждому сотруднику.

    Пример ответа:
    {
        "count": 1,
        "next": null,
        "previous": null,

        "results": [
            {
                "2024-10-29": {
                    "department": "Test",
                    "attendance": [
                        {
                            "staff_fio": "Иванов Иван",
                            "first_in": "2024-10-29T08:00:00+05:00",
                            "last_out": "2024-10-29T17:00:00+05:00",
                            "area_name": "Улица примерочная 1",
                            "remote_work": false,
                            "absence_reason": null
                        },
                        {
                            "staff_fio": "Петров Петр",
                            "first_in": "2024-10-29T09:15:00+05:00",
                            "last_out": "2024-10-29T16:45:00+05:00",
                            "area_name": "Проспект примеров 7",
                            "remote_work": true,
                            "absence_reason": "business_trip"
                        }
                    ]
                }
            },
            ...
        ]
    }

    Возможные ошибки:
    - 400: Не указаны параметры начала или конца периода.
    - 404: Подразделение не найдено или данные о посещаемости не найдены.
    - 500: Внутренняя ошибка сервера.
    """
    logger.info(
        f"Request received for staff attendance by department ID {department_id}"
    )

    try:
        end_date_str = request.query_params.get("end_date")
        start_date_str = request.query_params.get("start_date")
        page = request.query_params.get("page", 1)

        if not end_date_str or not start_date_str:
            logger.warning("Missing startDate or endDate in request parameters")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Не указаны параметры начала или конца периода"},
            )

        try:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            logger.info(
                f"Parsed date range: start_date={start_date}, end_date={end_date}"
            )
        except ValueError as ve:
            logger.warning(f"Invalid date format {ve}")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Неверный формат даты. Используйте YYYY-MM-DD."},
            )

        if start_date > end_date:
            logger.warning("Start date is greater than end date")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Дата начала не может быть больше даты конца"},
            )

        try:
            department = models.ChildDepartment.objects.get(id=department_id)
            logger.info(f"Department found: {department.name} (ID: {department_id})")
        except models.ChildDepartment.DoesNotExist:
            logger.warning(f"Department with ID {department_id} not found")
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"error": "Подразделение не найдено"},
            )

        def get_all_child_department_ids(department_id):
            """
            Uses a recursive CTE to get all child departments via an SQL query.

            Args:
                department_id (str): ID of the parent department.

            Returns:
                list: List of IDs of all child departments, including the given ID.
            """
            query = """
            WITH RECURSIVE childdepartment_cte AS (
                SELECT id, parent_id
                FROM monitoring_app_childdepartment
                WHERE id = %s
                UNION ALL
                SELECT cd.id, cd.parent_id
                FROM monitoring_app_childdepartment cd
                JOIN childdepartment_cte cte ON cd.parent_id = cte.id
            )
            SELECT id FROM childdepartment_cte;
            """
            with connection.cursor() as cursor:
                cursor.execute(query, [department_id])
                result = cursor.fetchall()
            return [row[0] for row in result]

        department_ids = get_all_child_department_ids(department_id)
        logger.info(f"Departments for ID {department_id}: {department_ids}")

        cache_key = (
            f"staff_detail_{department_id}_{start_date_str}_{end_date_str}_page_{page}"
        )
        logger.info(f"Generated cache key: {cache_key}")

        def daterange(start_date, end_date):
            for n in range(int((end_date - start_date).days) + 1):
                yield start_date + datetime.timedelta(n)

        REASON_DISPLAY = dict(models.AbsentReason.ABSENT_REASON_CHOICES)

        def query():
            logger.info("Querying staff attendance data")

            staff_objects = models.Staff.objects.filter(
                department_id__in=department_ids
            ).select_related("department")

            staff_dict = {staff.id: staff for staff in staff_objects}
            staff_ids = list(staff_dict.keys())

            staff_attendance_qs = (
                models.StaffAttendance.objects.filter(
                    staff_id__in=staff_ids,
                    date_at__range=(start_date, end_date),
                )
                .select_related("staff__department")
                .values("staff_id", "date_at", "first_in", "last_out", "area_name_in")
            )

            lesson_attendance_qs = (
                models.LessonAttendance.objects.filter(
                    staff_id__in=staff_ids,
                    date_at__range=(start_date, end_date),
                )
                .select_related("staff__department")
                .values(
                    "staff_id",
                    "date_at",
                    "first_in",
                    "last_out",
                    "latitude",
                    "longitude",
                )
            )

            absent_reasons_qs = (
                models.AbsentReason.objects.filter(
                    staff_id__in=staff_ids,
                    start_date__lte=end_date,
                    end_date__gte=start_date,
                )
                .select_related("staff")
                .values("staff_id", "reason", "start_date", "end_date")
            )
            logger.info(f"AbsentReason records fetched: {absent_reasons_qs.count()}")

            remote_works_qs = (
                models.RemoteWork.objects.filter(
                    Q(staff_id__in=staff_ids)
                    & (
                        Q(start_date__lte=end_date, end_date__gte=start_date)
                        | Q(permanent_remote=True)
                    )
                )
                .select_related("staff")
                .values("staff_id", "permanent_remote", "start_date", "end_date")
            )
            logger.debug(f"RemoteWork records fetched: {remote_works_qs.count()}")

            location_cache = get_class_location_cache()
            location_searcher = location_cache["searcher"]
            if location_searcher is None:
                location_searcher = utils.LocationSearcher(
                    location_cache["searcher_payload"] or []
                )

            staff_attendance_map = defaultdict(lambda: defaultdict(list))
            for sa in staff_attendance_qs:
                date_key = (sa["date_at"] - datetime.timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                )
                staff_attendance_map[sa["staff_id"]][date_key].append(sa)

            lesson_attendance_map = defaultdict(lambda: defaultdict(list))
            for la in lesson_attendance_qs:
                date_key = la["date_at"].strftime("%Y-%m-%d")
                lesson_attendance_map[la["staff_id"]][date_key].append(la)

            absence_map = defaultdict(lambda: defaultdict(list))
            for ar in absent_reasons_qs:
                ar_start = max(ar["start_date"], start_date)
                ar_end = min(ar["end_date"], end_date)
                for single_date in daterange(ar_start, ar_end):
                    date_key = single_date.strftime("%Y-%m-%d")
                    display_reason = REASON_DISPLAY.get(ar["reason"], ar["reason"])
                    absence_map[ar["staff_id"]][date_key].append(display_reason)

            remote_work_map = defaultdict(lambda: defaultdict(bool))
            for rw in remote_works_qs:
                if rw["permanent_remote"]:
                    rw_start = start_date
                    rw_end = end_date
                else:
                    raw_start = rw.get("start_date")
                    raw_end = rw.get("end_date")
                    tmp_start = raw_start if raw_start is not None else start_date
                    tmp_end = raw_end if raw_end is not None else end_date
                    rw_start = max(tmp_start, start_date)
                    rw_end = min(tmp_end, end_date)
                if rw_start <= rw_end:
                    for single_date in daterange(rw_start, rw_end):
                        date_key = single_date.strftime("%Y-%m-%d")
                        remote_work_map[rw["staff_id"]][date_key] = True

            results = []

            for single_date in daterange(start_date, end_date):
                date_key = single_date.strftime("%Y-%m-%d")

                department_attendance_map = defaultdict(list)

                for staff_id, staff in staff_dict.items():
                    staff_fio = f"{staff.surname} {staff.name}"
                    department_name = (
                        staff.department.name
                        if staff.department
                        else "Unknown Department"
                    )

                    sa_records = staff_attendance_map.get(staff_id, {}).get(
                        date_key, []
                    )
                    la_records = lesson_attendance_map.get(staff_id, {}).get(
                        date_key, []
                    )

                    first_in = None
                    last_out = None
                    area_names = []

                    for sa in sa_records:
                        if sa["first_in"]:
                            sa_first_in = sa["first_in"].astimezone(
                                timezone.get_default_timezone()
                            )
                            if not first_in or sa_first_in < first_in:
                                first_in = sa_first_in
                        if sa["last_out"]:
                            sa_last_out = sa["last_out"].astimezone(
                                timezone.get_default_timezone()
                            )
                            if not last_out or sa_last_out > last_out:
                                last_out = sa_last_out
                        area_address = utils.resolve_area_address(
                            sa.get("area_name_in")
                        )
                        if area_address:
                            area_names.append(area_address)

                    for la in la_records:
                        if la["first_in"]:
                            la_first_in = la["first_in"].astimezone(
                                timezone.get_default_timezone()
                            )
                            if not first_in or la_first_in < first_in:
                                first_in = la_first_in
                        if la["last_out"]:
                            la_last_out = la["last_out"].astimezone(
                                timezone.get_default_timezone()
                            )
                            if not last_out or la_last_out > last_out:
                                last_out = la_last_out

                        closest_location_name = location_searcher.find_nearest(
                            la["latitude"], la["longitude"], radius=200
                        )
                        if closest_location_name != "Unknown Area":
                            area_names.append(closest_location_name)

                    area_name = area_names[0] if area_names else "Unknown Area"

                    remote_work = remote_work_map.get(staff_id, {}).get(date_key, False)
                    reasons = absence_map.get(staff_id, {}).get(date_key, [])
                    absence_reason = ", ".join(reasons) if reasons else None

                    attendance_entry = {
                        "staff_fio": staff_fio,
                        "first_in": first_in.isoformat() if first_in else None,
                        "last_out": last_out.isoformat() if last_out else None,
                        "area_name": area_name,
                        "remote_work": remote_work,
                        "absence_reason": absence_reason,
                    }

                    department_attendance_map[department_name].append(attendance_entry)

                for dept, attendance in department_attendance_map.items():
                    date_result = {
                        date_key: {"department": dept, "attendance": attendance}
                    }
                    results.append(date_result)

            paginator = StaffAttendancePagination()
            result_page = paginator.paginate_queryset(results, request)
            return paginator.get_paginated_response(result_page).data

        cached_data = get_cache(cache_key, query=query, timeout=1 * 60 * 60)
        logger.info("Returning cached or queried data")
        return Response(cached_data)

    except Exception as e:
        logger.error(f"Server error while processing request: {str(e)}")
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data={"error": str(e)},
        )


@swagger_auto_schema(
    method="post",
    operation_summary="Зарегистрировать нового пользователя (доступно только для администратора)",
    operation_description="Регистрирует нового пользователя в системе. Разрешено только для администратора.",
    tags=["Authentication"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["username", "password"],
        properties={
            "username": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Желаемое имя для нового пользователя",
            ),
            "password": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Пароль для нового пользователя",
            ),
        },
    ),
    responses={
        201: openapi.Response(
            description="Created - Пользователь успешно зарегистрирован",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение о результате регистрации",
                    )
                },
            ),
        ),
        400: openapi.Response(
            description="Bad Request - Ошибка в запросе",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Описание ошибки запроса",
                    ),
                },
            ),
        ),
    },
)
@api_view(http_method_names=["POST"])
@permission_classes([IsAdminUser])
def user_register(request):
    """
    Регистрирует нового пользователя в системе. Разрешено только для администратора.

    Этот view ожидает запрос POST, содержащий в теле запроса следующие данные:
    - username (str): Желаемое имя для нового пользователя.
    - password (str): Пароль для нового пользователя.

    Возвращаемые данные:
    - status (int): HTTP статус код:
        - 201 Created: Если пользователь успешно зарегистрирован.
        - 400 Bad Request: Если имя пользователя или пароль отсутствуют, не соответствуют требованиям или имя пользователя уже занято.
    - message (str): Сообщение о результате регистрации.

    Возможные ошибки:
    - 400 Bad Request: Если имя пользователя или пароль отсутствуют, пароль не соответствует требованиям или имя пользователя уже занято.

    Исключения:
    - Стандартные исключения Django, если во время создания или сохранения пользователя возникают какие-либо ошибки.
    """

    logger.info("Received request to register a new user")

    username = request.data.get("username", None)
    password = request.data.get("password", None)

    if not username or not password:
        logger.warning("Username or password not provided")
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"message": "Требуется юзернейм и пароль"},
        )

    if not utils.password_check(password):
        logger.warning("Password does not meet the requirements")
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"message": "Пароль не прошел требования"},
        )

    try:
        user, created = User.objects.get_or_create(username=username)
        if not created:
            logger.warning(f"Username '{username}' is already taken")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"message": "Данный username уже занят"},
            )

        user.set_password(password)
        user.save()
        logger.info(f"User '{username}' successfully created")
        return Response(
            status=status.HTTP_201_CREATED,
            data={"message": "пользователь успешно создан"},
        )
    except Exception as e:
        logger.error(f"Error occurred while creating user '{username}': {str(e)}")
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data={"message": str(e)},
        )


def logout_view(request):
    logout(request)
    return redirect("login_view")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("uploadFile")

    return render(request, "login.html", context={})


@swagger_auto_schema(
    method="get",
    operation_summary="Запуск синхронизации посещаемости с внешним СКУД",
    operation_description=(
        "Запускает загрузку посещаемости сотрудников с внешнего сервера и сохранение в базу. "
        "Аутентификация: `X-API-KEY` или `Authorization: Bearer <access_token>`."
    ),
    tags=["Fetcher"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        token_param_config,
        openapi.Parameter(
            name="days",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_INTEGER,
            required=False,
            description=(
                "На сколько дней назад брать данные (0..365). "
                "Если не передан, используется значение из settings.DAYS."
            ),
        ),
        openapi.Parameter(
            name="max_concurrent_requests",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_INTEGER,
            required=False,
            description=(
                "Максимум одновременных запросов к внешнему API (1..30, по умолчанию 6)."
            ),
        ),
    ],
    responses={
        200: openapi.Response(
            description="Синхронизация завершена без ошибок.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Статус выполнения.",
                    ),
                    "days": openapi.Schema(
                        type=openapi.TYPE_INTEGER,
                        description="Фактически использованное значение days.",
                    ),
                    "duration_seconds": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        format=openapi.FORMAT_FLOAT,
                        description="Время выполнения в секундах.",
                    ),
                    "duration_human_readable": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Человекочитаемая длительность.",
                    ),
                    "status": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Статус выполнения: success/partial_error/failed.",
                    ),
                    "fetch_summary": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "source_date": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Дата источника (день, который запрашивали во внешнем API).",
                            ),
                            "save_date": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Дата, в которую сохранялись записи.",
                            ),
                            "total_pins": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "successful_requests": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "failed_requests": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "pins_with_events": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "pins_without_events": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "created_records": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "updated_records": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "event_time_parse_errors": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "error_statuses": openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                description="Сводка кодов ошибок внешнего API, например {'401': 12, 'network_or_unknown': 2}.",
                            ),
                        },
                    ),
                },
            ),
        ),
        207: openapi.Response(
            description="Синхронизация завершена частично: были ошибки по части PIN-ов.",
        ),
        400: openapi.Response(
            description="Некорректные query-параметры.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
        403: "Forbidden: Если доступ запрещен (нет валидной авторизации).",
        429: "Too Many Requests: Fetcher уже выполняется.",
        500: "Internal Server Error: Внутренняя ошибка сервера.",
        502: "Bad Gateway: Все обращения к внешнему API завершились ошибкой.",
    },
)
@async_logic.async_drf_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
async def fetch_data_view(request):
    """
    Асинхронный обработчик запросов на получение данных о посещаемости.
    """
    function_name = "fetch_data_view"
    start_time = time.perf_counter()
    logger.info("%s: Request received", function_name)
    lock_key = "attendance_fetcher_run_lock"
    lock_ttl_seconds = int(getattr(settings, "FETCHER_LOCK_TTL_SECONDS", 30 * 60))
    lock_acquired = cache.add(lock_key, "running", timeout=lock_ttl_seconds)

    if not lock_acquired:
        logger.warning(
            "%s: rejected because another fetcher run is in progress", function_name
        )
        return Response(
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            data={
                "status": "busy",
                "message": "Fetcher is already running. Try again later.",
            },
        )

    def parse_int_query_param(
        name: str,
        *,
        default: int | None,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> tuple[int | None, str | None]:
        raw_value = request.query_params.get(name)
        if raw_value in (None, ""):
            return default, None
        try:
            parsed_value = int(raw_value)
        except (TypeError, ValueError):
            return None, f"Параметр '{name}' должен быть целым числом."

        if min_value is not None and parsed_value < min_value:
            return (
                None,
                f"Параметр '{name}' должен быть не меньше {min_value}.",
            )
        if max_value is not None and parsed_value > max_value:
            return (
                None,
                f"Параметр '{name}' должен быть не больше {max_value}.",
            )
        return parsed_value, None

    try:
        has_api_key_header = bool(
            request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
        )
        if (
            request.user.is_authenticated
            and not request.user.is_staff
            and not has_api_key_header
        ):
            logger.warning(
                "%s: forbidden for non-staff authenticated user id=%s",
                function_name,
                request.user.id,
            )
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"error": "Недостаточно прав для запуска fetcher."},
            )

        days, days_error = parse_int_query_param(
            "days",
            default=None,
            min_value=0,
            max_value=365,
        )
        if days_error:
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data={"error": days_error}
            )

        max_concurrent_requests, concurrency_error = parse_int_query_param(
            "max_concurrent_requests",
            default=6,
            min_value=1,
            max_value=30,
        )
        if concurrency_error:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": concurrency_error},
            )
        if max_concurrent_requests is None:
            max_concurrent_requests = 6

        logger.info(
            "%s: Starting attendance fetch with params days=%s, max_concurrent_requests=%s",
            function_name,
            days,
            max_concurrent_requests,
        )

        fetcher = attendance_fetcher.AsyncAttendanceFetcher(
            max_concurrent_requests=max_concurrent_requests,
        )
        fetch_summary = await fetcher.get_all_attendance(days=days)
        raw_errors = fetch_summary.get("errors", [])

        error_statuses_counter: Counter[str] = Counter()
        if isinstance(raw_errors, list):
            for error in raw_errors:
                if not isinstance(error, dict):
                    error_statuses_counter["network_or_unknown"] += 1
                    continue
                status_value = error.get("status")
                if status_value is None:
                    error_statuses_counter["network_or_unknown"] += 1
                else:
                    error_statuses_counter[str(status_value)] += 1

        failed_requests = int(fetch_summary.get("failed_requests", 0))
        total_pins = int(fetch_summary.get("total_pins", 0))
        elapsed_seconds = time.perf_counter() - start_time
        duration_human_readable = utils.format_duration(elapsed_seconds)
        response_summary = {
            "source_date": fetch_summary.get("source_date"),
            "save_date": fetch_summary.get("save_date"),
            "total_pins": total_pins,
            "successful_requests": int(fetch_summary.get("successful_requests", 0)),
            "failed_requests": failed_requests,
            "pins_with_events": int(fetch_summary.get("pins_with_events", 0)),
            "pins_without_events": int(fetch_summary.get("pins_without_events", 0)),
            "created_records": int(fetch_summary.get("created_records", 0)),
            "updated_records": int(fetch_summary.get("updated_records", 0)),
            "event_time_parse_errors": int(
                fetch_summary.get("event_time_parse_errors", 0)
            ),
        }
        if error_statuses_counter:
            response_summary["error_statuses"] = dict(error_statuses_counter)

        response_data = {
            "message": "Done",
            "status": "success",
            "days": fetch_summary.get("days", days),
            "duration_seconds": round(elapsed_seconds, 2),
            "duration_human_readable": duration_human_readable,
            "fetch_summary": response_summary,
        }

        if failed_requests == 0:
            response_status = status.HTTP_200_OK
            response_data["message"] = "Done"
        elif failed_requests < total_pins:
            response_status = status.HTTP_207_MULTI_STATUS
            response_data["status"] = "partial_error"
            response_data["message"] = "Done with errors."
        else:
            response_status = status.HTTP_502_BAD_GATEWAY
            response_data["status"] = "failed"
            response_data["message"] = "Fetcher failed."

        logger.info(
            "%s: Completed with status=%s in %.2f seconds (total_pins=%s, failed_requests=%s)",
            function_name,
            response_status,
            elapsed_seconds,
            total_pins,
            failed_requests,
        )

        return Response(status=response_status, data=response_data)

    except Exception as e:
        elapsed_seconds = time.perf_counter() - start_time
        duration_human_readable = utils.format_duration(elapsed_seconds)
        logger.error(
            f"{function_name}: Error occurred while fetching attendance data: {str(e)}",
            exc_info=True,
        )
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data={
                "status": "failed",
                "error": "Ошибка при выполнении fetcher.",
                "duration_seconds": round(elapsed_seconds, 2),
                "duration_human_readable": duration_human_readable,
            },
        )
    finally:
        if lock_acquired:
            cache.delete(lock_key)


@swagger_auto_schema(
    method="get",
    operation_summary="Generate Attendance Excel File",
    operation_description=(
        "Generates an Excel file containing attendance data for the specified department and its child departments. "
        "You must provide the department ID as a path parameter, and the report period via the `startDate` and `endDate` "
        "query parameters formatted as YYYY-MM-DD. If the provided endDate is greater than today, it will be capped to today's date. "
        "Authentication is required by providing a valid API key in the X-API-KEY header or by using other credentials."
    ),
    tags=["Files & Downloads"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=False,
            description="API ключ для аутентификации (альтернатива JWT токену).",
        ),
        openapi.Parameter(
            name="department_id",
            in_=openapi.IN_PATH,
            type=openapi.TYPE_INTEGER,
            required=True,
            description="The ID of the department for which the attendance report is to be generated.",
        ),
        openapi.Parameter(
            name="startDate",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            format="date",
            required=True,
            description="The start date of the attendance report period, formatted as YYYY-MM-DD.",
        ),
        openapi.Parameter(
            name="endDate",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            format="date",
            required=True,
            description="The end date of the attendance report period, formatted as YYYY-MM-DD.",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Excel file generated successfully. Returns an Excel file stream.",
            examples={
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Binary Excel data"
            },
        ),
        400: "Bad Request: Missing or invalid query parameters (startDate, endDate) or date format issues.",
        404: "Not Found: The specified department or associated staff records were not found.",
        500: "Internal Server Error: Failed to generate the Excel file due to a server error.",
    },
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticatedOrAPIKey])
def sent_excel(request, department_id):
    """
    Optimized function for generating and returning attendance Excel files.

    Args:
        request: HTTP request object
        department_id: ID of the department to generate report for

    Returns:
        HttpResponse with Excel file or error Response
    """
    start_time = datetime.datetime.now()
    logger.info(f"Starting Excel generation for department ID {department_id}")

    end_date_str = request.query_params.get("endDate")
    start_date_str = request.query_params.get("startDate")

    if not all([end_date_str, start_date_str]):
        logger.warning(
            f"Missing startDate or endDate in request for department ID {department_id}"
        )
        return Response(
            {"error": "Missing startDate or endDate"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()

        today = datetime.datetime.now().date()
        if end_date > today:
            logger.info(f"Capping end_date from {end_date} to {today}")
            end_date = today

        if start_date > end_date:
            logger.warning(f"Start date {start_date} is after end date {end_date}")
            return Response(
                {"error": "Start date cannot be after end date"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return Response(
            {"error": f"Invalid date format: {e}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        department = models.ChildDepartment.objects.get(id=department_id)
        logger.info(f"Department found: {department.name}")
    except models.ChildDepartment.DoesNotExist:
        logger.warning(f"Department with ID {department_id} not found")
        return Response(
            {"error": "Department not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    all_departments = utils.get_all_child_departments(department)
    department_ids = [dept.id for dept in all_departments]
    logger.info(f"Found {len(department_ids)} departments in hierarchy")

    staff_list = models.Staff.objects.filter(
        department_id__in=department_ids
    ).select_related("department")
    if not staff_list.exists():
        logger.warning(
            f"No staff found for department ID {department_id} or its children"
        )
        return Response(
            {"error": "No staff found for this department"},
            status=status.HTTP_404_NOT_FOUND,
        )

    attendance_data = utils.collect_attendance_data(staff_list, start_date, end_date)

    try:
        excel_file = utils.generate_excel_file(
            attendance_data, department.name, start_date, end_date
        )

        processing_time = datetime.datetime.now() - start_time
        logger.info(
            f"Excel file generated in {utils.format_duration(processing_time.total_seconds())}"
        )

        response = HttpResponse(
            excel_file,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = (
            f"attachment; filename=Attendance_{department_id}_{start_date_str}_{end_date_str}.xlsx"
        )
        return response

    except Exception as e:
        logger.error(f"Error generating Excel file: {str(e)}", exc_info=True)
        return Response(
            {"error": "Failed to generate Excel file: " + str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class UploadFileView(View):
    """
    Класс представления для обработки действий по загрузке файлов.

    Отображает форму загрузки файла (upload_file.html)
    и обрабатывает POST-запросы для импорта данных из файла.
    """

    template_name = "upload_file.html"

    def get(self, request, *args, **kwargs):
        """
        Обрабатывает GET-запросы.

        Args:
            request (HttpRequest): Объект запроса.
            *args: Дополнительные позиционные аргументы.
            **kwargs: Дополнительные именованные аргументы.

        Returns:
            HttpResponse: Отрисовывает шаблон upload_file.html
            с контекстом, содержащим список всех категорий файлов (categories) и список родительских отделов (parent_departments).
        """
        logger.info("GET request received for file upload view")
        categories = models.FileCategory.objects.all()
        parent_departments = models.ParentDepartment.objects.exclude(id=1)
        context = {"categories": categories, "parent_departments": parent_departments}
        logger.debug(f"Rendering template with context: {context}")
        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        """
        Обрабатывает POST-запросы.

        Args:
            request (HttpRequest): Объект запроса.
            *args: Дополнительные позиционные аргументы.
            **kwargs: Дополнительные именованные аргументы.

        Returns:
            HttpResponse: Возвращает редирект на страницу загрузки файла или
            рендеринг upload_file.html с соответствующим контекстом.

        Raises:
            Exception: Если произошла ошибка при обработке файла.
        """
        logger.info("POST request received for file upload view")
        file_path = request.FILES.get("file")
        category_slug = request.POST.get("category")
        parent_department_id = request.POST.get("parent_department")

        if file_path and category_slug:
            logger.debug(f"File received: {file_path.name}, Category: {category_slug}")
            try:
                if file_path.name.endswith(".xlsx"):
                    logger.info("Processing Excel file")
                    rows = self.handle_excel(file_path)
                    if category_slug == "delete_staff":
                        logger.info("Deleting staff based on Excel data")
                        self.delete_staff(request, rows, parent_department_id)
                    elif category_slug == "staff":
                        logger.info("Processing staff data from Excel")
                        self.process_staff(request, rows)
                    elif category_slug == "departments":
                        logger.info("Processing departments data from Excel")
                        self.process_departments(request, rows)
                    elif category_slug == "public_holidays":
                        logger.info("Processing public holidays data from Excel")
                        self.process_public_holidays(request, rows)
                    elif category_slug == "load_geo":
                        rows = rows[1:]
                        logger.info("Processing ClassLocation data from Excel")
                        self.process_class_locations(request, rows)
                    messages.success(
                        request, "Файл успешно обработан и данные обновлены."
                    )
                elif file_path.name.endswith(".zip") and category_slug == "photo":
                    logger.info("Processing ZIP file for photos")
                    self.handle_zip(request, file_path)
                    messages.success(request, "Фото успешно загружены.")
                else:
                    logger.warning("Invalid file format or category")
                    messages.error(request, "Неверный формат файла или категория.")
                    return render(request, self.template_name)

                return redirect("uploadFile")
            except Exception as error:
                logger.error(f"Error processing file: {str(error)}")
                messages.error(request, f"Ошибка при обработке файла: {str(error)}")
        else:
            logger.warning("File or category missing in the POST request")
            messages.error(
                request,
                "Проверьте правильность заполненных данных или неверный формат файла.",
            )

        return render(request, self.template_name)

    def handle_excel(self, file_path) -> List[ExcelRow]:
        """
        Обрабатывает загрузку и импорт данных из файла Excel.

        Args:
            file_path (File): Путь к загруженному файлу.
            category_slug (str): Категория файла для обработки.

        Raises:
            Exception: Если произошла ошибка при обработке файла Excel.
        """
        logger.info("Handling Excel file")
        try:
            with atomic_block():
                wb = load_workbook(file_path)
                ws = wb.active
                ws.delete_rows(1, 2)
                rows = list(ws.iter_rows())
                logger.debug(f"Rows before sorting: {[row[0].value for row in rows]}")

                rows.sort(
                    key=lambda row: (
                        not str(row[0].value).isdigit(),
                        str(row[0].value).zfill(10),
                    ),
                    reverse=False,
                )
                logger.debug(f"Rows after sorting: {[row[0].value for row in rows]}")
                logger.debug(f"Excel file processed, number of rows: {len(rows)}")
                return rows
        except Exception as e:
            logger.error(f"Error processing Excel file: {str(e)}")
            raise

    def process_class_locations(self, request, rows):
        """
        Processes a list of Excel file rows to populate the ClassLocation model using bulk_create and bulk_update.

        This method processes rows containing class location data, extracting details such as
        name, address, latitude, and longitude. It then either creates new ClassLocation records
        or updates existing ones based on matching name and address. Records with missing or invalid
        data are skipped, and errors are logged.

        Args:
            request (HttpRequest): The request object.
            rows (list): A list of Excel rows, where each row contains data in the format
                [name, address, geo].

        Raises:
            ValueError: If the 'geo' column value is missing or invalid.

        Returns:
            None: Populates the ClassLocation model and sends success or error messages
            to the request user regarding records that were created, updated, or skipped due to errors.

        Logs:
            Logs details of processed rows, including created, updated, and skipped rows. If errors
            occur, they are logged and the user is notified.
        """
        with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
            to_create = []
            to_update = []
            existing_locations = {
                (loc.name, loc.address): loc
                for loc in models.ClassLocation.objects.only(
                    "id",
                    "name",
                    "address",
                    "latitude",
                    "longitude",
                    "acceptance_radius_m",
                )
            }

            error_count = 0
            error_details = []
            MAX_ERROR_DETAILS = 10

            for index, row in enumerate(rows):
                try:
                    name = str(row[0].value or "").strip()
                    address = str(row[1].value or "").strip()
                    geo_data = str(row[2].value or "") if len(row) > 2 else ""
                    radius_val = row[3].value if len(row) > 3 else None

                    if not geo_data or geo_data.lower() == "none":
                        raise ValueError("Отсутствует значение в столбце 'geo'.")

                    latitude, longitude = utils.extract_coordinates(geo_data)

                    if not all([name, address, latitude, longitude]):
                        raise ValueError("Отсутствуют необходимые данные.")

                    try:
                        if latitude is None or str(latitude).strip() == "":
                            raise ValueError("Latitude is missing or empty")
                        if longitude is None or str(longitude).strip() == "":
                            raise ValueError("Longitude is missing or empty")

                        lat_str = (
                            latitude
                            if isinstance(latitude, (int, float))
                            else str(latitude).strip().replace(",", ".")
                        )
                        lon_str = (
                            longitude
                            if isinstance(longitude, (int, float))
                            else str(longitude).strip().replace(",", ".")
                        )

                        latitude = float(lat_str)
                        longitude = float(lon_str)
                    except (TypeError, ValueError) as e:
                        raise ValueError(f"Invalid coordinates: {e}")

                    acceptance_radius_m = None
                    if radius_val is not None and str(radius_val).strip() != "":
                        try:
                            acceptance_radius_m = int(float(str(radius_val).strip()))
                            if acceptance_radius_m <= 0:
                                acceptance_radius_m = None
                        except (TypeError, ValueError):
                            pass

                    if (name, address) in existing_locations:
                        location = existing_locations[(name, address)]
                        location.latitude = latitude
                        location.longitude = longitude
                        if acceptance_radius_m is not None:
                            location.acceptance_radius_m = acceptance_radius_m
                        to_update.append(location)
                    else:
                        loc_kw = dict(
                            name=name,
                            address=address,
                            latitude=latitude,
                            longitude=longitude,
                        )
                        if acceptance_radius_m is not None:
                            loc_kw["acceptance_radius_m"] = acceptance_radius_m
                        to_create.append(models.ClassLocation(**loc_kw))
                except Exception as e:
                    logger.error(f"Error processing row {index} for ClassLocation: {e}")
                    error_count += 1
                    if len(error_details) < MAX_ERROR_DETAILS:
                        error_details.append(f"Строка {index + 2}: {e}")
                    continue

            if to_create:
                try:
                    models.ClassLocation.objects.bulk_create(to_create)
                    logger.info(f"Создано новых записей: {len(to_create)}")
                except Exception as e:
                    logger.error(f"Error during bulk_create: {e}")
                    messages.error(
                        request, "Не удалось создать новые записи ClassLocation."
                    )

            if to_update:
                try:
                    models.ClassLocation.objects.bulk_update(
                        to_update, ["latitude", "longitude", "acceptance_radius_m"]
                    )
                    logger.info(f"Обновлено существующих записей: {len(to_update)}")
                except Exception as e:
                    logger.error(f"Error during bulk_update: {e}")
                    messages.error(
                        request,
                        "Не удалось обновить существующие записи ClassLocation.",
                    )

            if to_create or to_update:
                try:
                    invalidate_class_location_cache_impl()
                except Exception as inv_err:
                    logger.warning(f"Cache invalidation after bulk ops: {inv_err}")

            success_message = f"Успешно добавлено {len(to_create)} новых записей и обновлено {len(to_update)} записей."
            if error_count > 0:
                success_message += f" Пропущено {error_count} записей из-за ошибок."
            messages.success(request, success_message)

            if error_details:
                error_message = (
                    "Некоторые записи были пропущены из-за ошибок:\n"
                    + "\n".join(error_details)
                )
                if error_count > MAX_ERROR_DETAILS:
                    error_message += (
                        f"\n...и ещё {error_count - MAX_ERROR_DETAILS} ошибок."
                    )
                messages.warning(request, error_message)

    def delete_staff(self, request, rows, parent_department_id):
        """
        Удаляет сотрудников дочерних отделов, отсутствующих в переданном списке PIN-кодов.

        Метод получает родительский отдел по `parent_department_id` и находит все связанные
        дочерние отделы. Затем проверяет, какие PIN-коды сотрудников из базы данных
        отсутствуют в списке, переданном в `rows`, и удаляет таких сотрудников.

        Args:
            request: HTTP-запрос для отправки сообщений об успешном или неудачном удалении.
            rows: Список строк с PIN-кодами сотрудников, которых нужно оставить.
            parent_department_id: ID родительского отдела для поиска связанных дочерних отделов.

        Exceptions:
            ValueError: Если не передан `parent_department_id` или не найдены дочерние отделы.
            models.ParentDepartment.DoesNotExist: Если родительский отдел с данным ID не найден.
            Exception: Любая другая ошибка, возникшая при удалении сотрудников.
        """
        logger.info(f"Deleting staff for parent department ID: {parent_department_id}")
        try:
            if not parent_department_id:
                raise ValueError("ID родительского отдела не был передан.")

            parent_department = models.ParentDepartment.objects.get(
                id=parent_department_id
            )

            child_departments = models.ChildDepartment.objects.filter(
                parent__name=parent_department.name
            )
            if not child_departments.exists():
                raise ValueError(
                    f"Для родительского отдела {parent_department.name} не найдены дочерние отделы."
                )

            pin_list_from_file = [row[0].value for row in rows if row[0].value]

            staff_in_db = models.Staff.objects.filter(department__in=child_departments)

            staff_to_delete = staff_in_db.exclude(pin__in=pin_list_from_file)

            deleted_count, _ = staff_to_delete.delete()
            logger.info(f"Deleted {deleted_count} staff members")
            messages.success(
                request, f"Успешно удалено {deleted_count} сотрудника(ов)."
            )

        except models.ParentDepartment.DoesNotExist:
            error_message = f"Родительский отдел с ID {parent_department_id} не найден."
            logger.error(error_message)
            messages.error(request, error_message)
        except ValueError as ve:
            logger.warning(f"ValueError during staff deletion: {str(ve)}")
            messages.error(request, str(ve))
        except Exception as e:
            logger.error(f"Unexpected error during staff deletion: {str(e)}")
            messages.error(
                request, f"Произошла ошибка при удалении сотрудников: {str(e)}"
            )

    def process_departments(self, request, rows):
        """
        Обрабатывает данные для категории "departments" из Excel файла.
        Args:
            rows (list): Список строк из файла Excel.
        Raises:
            Exception: Если произошла ошибка при обработке строки.
        """
        logger.info("Processing departments data")

        created_parent_departments = []
        created_child_departments = []

        try:
            for row in rows:
                parent_department_id_value = row[2].value
                parent_department_name = row[3].value
                child_department_name = row[1].value
                child_department_id_value = row[0].value

                parent_department_id = (
                    utils.normalize_id(str(parent_department_id_value).strip())
                    if parent_department_id_value
                    else None
                )
                child_department_id = (
                    utils.normalize_id(str(child_department_id_value).strip())
                    if child_department_id_value
                    else None
                )

                if not parent_department_id or not child_department_id:
                    logger.debug("Skipping row due to missing or invalid ID")
                    continue

                if parent_department_name:
                    (
                        parent_department,
                        parent_created,
                    ) = models.ParentDepartment.objects.get_or_create(
                        id=parent_department_id,
                        defaults={"name": parent_department_name},
                    )
                    if parent_created:
                        created_parent_departments.append(parent_department_name)
                        logger.info(
                            f"Created new parent department: {parent_department_name}"
                        )

                    (
                        parent_department_as_child,
                        child_created,
                    ) = models.ChildDepartment.objects.get_or_create(
                        id=parent_department.id,
                        defaults={"name": parent_department.name, "parent": None},
                    )
                else:
                    parent_department_as_child = models.ChildDepartment.objects.get(
                        id="1"
                    )

                (
                    _child_department,
                    child_created,
                ) = models.ChildDepartment.objects.get_or_create(
                    id=child_department_id,
                    defaults={
                        "name": child_department_name,
                        "parent": parent_department_as_child,
                    },
                )
                if child_created:
                    created_child_departments.append(child_department_name)
                    logger.info(
                        f"Created new child department: {child_department_name}"
                    )

            if created_parent_departments or created_child_departments:
                messages.success(
                    request,
                    f"Создано родительских отделов: {len(created_parent_departments)}, "
                    f"дочерних отделов: {len(created_child_departments)}.",
                )

        except Exception as error:
            logger.error(f"Error processing departments: {str(error)}")
            messages.error(request, f"Ошибка при обработке отдела: {str(error)}")

    def process_staff(self, request, rows):
        """
        Обрабатывает данные для категории "staff" из Excel файла.
        except Exception as error:
            messages.error(request, f"Ошибка при обработке отдела: {str(error)}")

        Args:
            rows (list): Список строк из файла Excel.

        Raises:
            Exception: Если произошла ошибка при обработке строки.
        """
        logger.info("Processing staff data")
        staff_instances = []
        departments_cache = {}

        try:
            for row in rows:
                pin = row[0].value
                name = row[1].value
                surname = row[2].value or "Нет фамилии"
                department_id = str(row[3].value) if row[3].value else None
                position_name = (
                    row[5].value or "Сотрудник" if len(row) > 5 else "Сотрудник"
                )

                position, _ = models.Position.objects.get_or_create(name=position_name)

                if department_id:
                    if department_id in departments_cache:
                        department = departments_cache[department_id]
                    else:
                        try:
                            department = models.ChildDepartment.objects.get(
                                id=department_id
                            )
                            departments_cache[department_id] = department
                        except models.ChildDepartment.DoesNotExist:
                            department = None
                else:
                    department = None

                staff_instance = models.Staff(
                    pin=pin,
                    name=name,
                    surname=surname,
                    department=department,
                )

                staff_instances.append((staff_instance, position))

            pin_list = [staff[0].pin for staff in staff_instances]
            existing_staff = models.Staff.objects.filter(pin__in=pin_list)
            existing_staff_dict = {staff.pin: staff for staff in existing_staff}

            staff_to_create = []
            staff_to_update = []

            for staff_instance, position in staff_instances:
                if staff_instance.pin in existing_staff_dict:
                    existing = existing_staff_dict[staff_instance.pin]
                    if staff_instance.name and staff_instance.name != existing.name:
                        existing.name = staff_instance.name
                    if (
                        staff_instance.surname
                        and staff_instance.surname != existing.surname
                    ):
                        existing.surname = staff_instance.surname
                    if (
                        staff_instance.department
                        and staff_instance.department != existing.department
                    ):
                        existing.department = staff_instance.department
                    if position.name and position.name != "Сотрудник":
                        if not existing.positions.filter(name=position.name).exists():
                            existing.positions.add(position)
                    staff_to_update.append(existing)
                else:
                    try:
                        staff_instance.save()
                        staff_instance.positions.add(position)
                        staff_to_create.append(staff_instance)
                    except IntegrityError:
                        logger.warning(
                            f"Duplicate entry for pin {staff_instance.pin}, skipping."
                        )
                        continue

            for staff in staff_to_update:
                staff.save()

            logger.info(f"Updated {len(staff_to_update)} staff members")
            logger.info(f"Created {len(staff_to_create)} new staff members")
            messages.success(
                request, f"Успешно обновлено {len(staff_to_update)} сотрудников."
            )
            messages.success(
                request, f"Успешно добавлено {len(staff_to_create)} новых сотрудников."
            )

        except Exception as e:
            logger.error(f"Error processing staff data: {str(e)}")
            messages.error(request, f"Ошибка при обработке сотрудников: {str(e)}")

    def process_public_holidays(self, request, rows):
        """
        Обрабатывает данные для категории "public_holidays" из Excel файла.

        Args:
            request (HttpRequest): Объект запроса.
            rows (list): Список строк из файла Excel.

        Raises:
            Exception: Если произошла ошибка при обработке строки.
        """
        logger.info("Processing public holidays data")

        created_holidays = 0
        updated_holidays = 0
        errors = []
        MAX_ERROR_DETAILS = 10

        WORKING_DAY_MAPPING = {
            "да": True,
            "нет": False,
            "yes": True,
            "no": False,
            "true": True,
            "false": False,
            "рабочий": True,
            "не рабочий": False,
        }

        with atomic_block():
            for index, row in enumerate(rows):
                try:
                    date_cell = row[0].value
                    name_cell = row[1].value
                    is_working_day_cell = row[2].value

                    if not date_cell or not name_cell:
                        raise ValueError(
                            "Отсутствуют обязательные поля 'Дата праздника' или 'Название праздника'."
                        )

                    if isinstance(date_cell, datetime.datetime) or isinstance(
                        date_cell, datetime.date
                    ):
                        date = (
                            date_cell.date()
                            if isinstance(date_cell, datetime.datetime)
                            else date_cell
                        )
                    else:
                        try:
                            date = datetime.datetime.strptime(
                                str(date_cell), "%d.%m.%Y"
                            ).date()
                        except ValueError:
                            try:
                                date = datetime.datetime.strptime(
                                    str(date_cell), "%Y-%m-%d"
                                ).date()
                            except ValueError:
                                raise ValueError(
                                    "Неверный формат даты. Ожидается DD.MM.YYYY или YYYY-MM-DD."
                                )

                    if isinstance(is_working_day_cell, bool):
                        is_working_day = is_working_day_cell
                    else:
                        is_working_day_str = str(is_working_day_cell).strip().lower()
                        is_working_day = WORKING_DAY_MAPPING.get(is_working_day_str)
                        if is_working_day is None:
                            raise ValueError(
                                "Неверное значение в поле 'Рабочий день'. Ожидается 'Да' или 'Нет'."
                            )

                    _holiday, created = models.PublicHoliday.objects.update_or_create(
                        date=date,
                        defaults={
                            "name": name_cell.strip(),
                            "is_working_day": is_working_day,
                        },
                    )

                    if created:
                        created_holidays += 1
                    else:
                        updated_holidays += 1

                except Exception as e:
                    logger.error(
                        f"Error processing row {index + 2} for PublicHoliday: {e}"
                    )
                    errors.append(f"Строка {index + 2}: {e}")
                    if len(errors) >= MAX_ERROR_DETAILS:
                        break
                    continue

        success_message = f"Успешно создано {created_holidays} праздников и обновлено {updated_holidays} праздников."
        messages.success(request, success_message)

        if errors:
            error_message = (
                "Некоторые записи не были обработаны из-за ошибок:\n"
                + "\n".join(errors)
            )
            if len(errors) > MAX_ERROR_DETAILS:
                error_message += f"\n...и ещё {len(errors) - MAX_ERROR_DETAILS} ошибок."
            messages.warning(request, error_message)

    def handle_zip(self, request, file_path):
        """
        Обрабатывает загрузку и импорт данных из ZIP архива для Staff.
        Args:
            file_path (File): Путь к загруженному файлу.

        Raises:
            Exception: Если произошла ошибка при обработке ZIP файла.
        """
        logger.info("Processing ZIP file for staff photos")
        try:
            with zipfile.ZipFile(file_path, "r") as zip_file:
                zip_file.extractall("/tmp")
                for filename in zip_file.namelist():
                    pin = os.path.splitext(filename)[0]
                    staff_member = models.Staff.objects.filter(pin=pin).first()
                    if staff_member:
                        with zip_file.open(filename) as file:
                            new_avatar = ContentFile(file.read())
                            new_avatar.name = filename
                            if new_avatar:
                                if staff_member.avatar:
                                    staff_member.avatar.delete(save=False)
                                staff_member.avatar.save(
                                    new_avatar.name, new_avatar, save=False
                                )
                                staff_member.save()
            logger.info("Staff photos updated successfully")
            messages.success(request, "Фотографии успешно обновлены.")
        except Exception as e:
            logger.error(f"Error processing ZIP file: {str(e)}")
            messages.error(
                request, f"Ошибка при обработке архива с фотографиями: {str(e)}"
            )


class APIKeyCheckView(APIView):
    """
    Проверка API ключа.

    Проверяет наличие и валидность переданного API ключа в заголовке запроса.
    Если ключ отсутствует или недействителен, возвращает соответствующее сообщение об ошибке.

    Методы:
        get: Проверяет API ключ и возвращает данные о его создании и статусе активности.

    Права доступа:
        AllowAny: Доступ открыт для всех пользователей, аутентификация не требуется.
    """

    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Проверка API ключа",
        operation_description="Проверяет наличие и валидность переданного API ключа в заголовке запроса.",
        tags=["Authentication"],
        manual_parameters=[
            openapi.Parameter(
                name="X-API-KEY",
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                required=True,
                description="API ключ для проверки.",
            )
        ],
        responses={
            200: openapi.Response(
                description="Данные о создании и статусе активности API ключа.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "data": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "created_at": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format="date-time",
                                    description="Дата и время создания ключа.",
                                ),
                                "is_active": openapi.Schema(
                                    type=openapi.TYPE_BOOLEAN,
                                    description="Статус активности ключа.",
                                ),
                            },
                        )
                    },
                ),
            ),
            400: openapi.Response(
                description="Некорректный запрос: отсутствует или недействителен API ключ.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Сообщение об ошибке.",
                        ),
                        "error": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Описание ошибки.",
                        ),
                    },
                ),
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        """
        Проверяет API ключ и возвращает данные о его создании и статусе активности.

        Аргументы:
            request (HttpRequest): Объект HTTP запроса.

        Возвращает:
            Response: Ответ с данными о создании и статусе активности API ключа, либо сообщение об ошибке.
        """
        logger.info("API Key check request received")

        api_key = request.headers.get("X-API-KEY")

        if not api_key:
            logger.warning("API Key is missing in the request")
            return Response(
                {"message": "API Key is missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            secret_key = utils.APIKeyUtility.get_secret_key()
            logger.debug("Secret key retrieved successfully")
            data = utils.APIKeyUtility.decrypt_data(
                api_key, secret_key, fields=("created_at", "is_active")
            )
            logger.info("API Key is valid")
            return Response({"data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Invalid API Key: {str(e)}")
            return Response(
                {"message": "Invalid API Key", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


def password_reset_request_view(request):
    if request.method == "POST":
        identifier = request.POST.get("identifier")
        ip_address = utils.get_client_ip(request)
        logger.error(str(ip_address))
        user = (
            User.objects.filter(username=identifier).first()
            or User.objects.filter(email=identifier).first()
        )

        user_timezone = utils.get_user_timezone(request)

        if user:
            last_request_time = models.PasswordResetRequestLog.get_last_request_time(
                user, ip_address
            )
            if not models.PasswordResetRequestLog.can_request_again(user, ip_address):
                if last_request_time:
                    next_possible_time = timezone.localtime(
                        last_request_time + timezone.timedelta(minutes=5),
                        user_timezone,
                    )
                    last_request_time_local = timezone.localtime(
                        last_request_time, user_timezone
                    )
                    messages.warning(
                        request,
                        f"Запрос уже был отправлен. Повторный запрос возможен в {next_possible_time.strftime('%H:%M:%S %Z')} ({next_possible_time.tzinfo}). Последний запрос был в {last_request_time_local.strftime('%H:%M:%S %Z')} ({last_request_time_local.tzinfo}).",
                    )
                else:
                    current_time_local = timezone.localtime(
                        timezone.now(), user_timezone
                    )
                    messages.warning(
                        request,
                        f"Запрос уже был отправлен. Повторный запрос возможен в ближайшее время. Последний запрос: неизвестен. Текущее время {current_time_local.strftime('%H:%M:%S %Z')} ({current_time_local.tzinfo}).",
                    )
            else:
                utils.send_password_reset_email(user, request)
                models.PasswordResetRequestLog.log_request(user, ip_address)
                current_time_local = timezone.localtime(timezone.now(), user_timezone)
                messages.success(
                    request,
                    f"Если пользователь существует, ссылка для сброса пароля была отправлена на его электронную почту. Последний запрос был в {current_time_local.strftime('%H:%M:%S %Z')} ({current_time_local.tzinfo}).",
                )
        else:
            messages.info(
                request,
                "Если пользователь существует, ссылка для сброса пароля была отправлена на его электронную почту.",
            )

        return redirect("password_reset_request")

    return render(request, "password_reset_request.html")


def password_reset_confirm_view(request, token):
    reset_token = get_object_or_404(models.PasswordResetToken, token=token)

    if not reset_token.is_valid():
        messages.error(request, "Этот токен для сброса пароля больше не действителен.")
        return redirect("password_reset_request")

    if request.method == "POST":
        new_password = request.POST.get("password")
        user = reset_token.user
        user.set_password(new_password)
        user.save()

        if models.PasswordResetToken.objects.mark_as_used(token):
            messages.success(
                request,
                "Пароль успешно сброшен. Вы можете войти в систему с новым паролем.",
            )
            return redirect("react_app")
        else:
            messages.error(request, "Ошибка при обновлении токена. Попробуйте снова.")
            return redirect("password_reset_confirm", token=token)

    return render(request, "password_reset_confirm.html", {"token": token})


def download_examples_zip(request):
    """
    Serve the 'examples.zip' file from the media directory to the user for download.

    This view checks for the existence of 'examples.zip' in the MEDIA_ROOT directory
    and serves it as a downloadable file if found. Logs an error and raises a 404
    error if the file is missing.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        FileResponse: A response object containing the file for download.

    Raises:
        Http404: If the file does not exist in the specified directory.
    """
    file_path = Path(settings.MEDIA_ROOT) / "examples.zip"

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        raise Http404("Requested file does not exist.")

    try:
        response = FileResponse(file_path.open("rb"), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="examples.zip"'
        return response
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}")
        raise Http404("An error occurred while serving the file.")


@swagger_auto_schema(
    method="post",
    auto_schema=FormOnlySwaggerAutoSchema,  # type: ignore[reportArgumentType]
    operation_summary="Верификация лица",
    operation_description="Верифицирует лицо сотрудника по PIN и изображению. Требует передачи заголовка X-API-KEY для просмотра в Swagger.",
    tags=["Face Recognition - Verify"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=True,
            description="API ключ для доступа к этому эндпоинту. Без этого ключа эндпоинт скрыт в Swagger.",
        ),
        openapi.Parameter(
            name="pin",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            required=True,
            description="PIN сотрудника для верификации.",
        ),
        openapi.Parameter(
            name="image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Изображение лица для верификации.",
        ),
    ],
    request_body=no_body,
    responses={
        200: openapi.Response(
            description="Результат верификации",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "verified": openapi.Schema(
                        type=openapi.TYPE_BOOLEAN,
                        description="Результат верификации (True/False).",
                    ),
                    "score": openapi.Schema(
                        type=openapi.TYPE_NUMBER,
                        description="Оценка схожести (0-1).",
                    ),
                },
            ),
        ),
        400: "Bad Request: Неверные данные запроса.",
        404: "Not Found: Сотрудник не найден.",
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_face(request):
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    face_logger = logging.getLogger("django")
    face_logger.info("Received request to verify face.")

    staff_pin = request.data.get("pin")
    staff_image = request.FILES.get("image")

    if not staff_pin or not staff_image:
        face_logger.warning("PIN or image is missing in the request.")
        return Response(
            {"error": "PIN and image are required."}, status=status.HTTP_400_BAD_REQUEST
        )

    if staff_image.size == 0:
        face_logger.warning("Uploaded image is empty.")
        return Response(
            {"error": "Uploaded image is empty."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        staff = models.Staff.objects.get(pin=staff_pin)
        face_logger.info(f"Staff with PIN {staff_pin} found.")
    except models.Staff.DoesNotExist:
        face_logger.error(f"Staff with PIN {staff_pin} does not exist.")
        return Response({"error": "Staff not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        face_mask = staff.face_mask
        face_logger.info(f"Face mask for staff with PIN {staff_pin} found.")
    except models.StaffFaceMask.DoesNotExist:
        face_logger.error(f"Face mask for staff with PIN {staff_pin} does not exist.")
        return Response(
            {"error": "Face mask for this staff member are not found."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not face_mask.mask_encoding:
        face_logger.error(f"Face embeddings for staff with PIN {staff_pin} are empty.")
        return Response(
            {"error": "Face embeddings for this staff member are empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        new_image = ml.load_image_from_memory(staff_image)
        new_embedding = ml.create_face_encoding(new_image)
        if new_embedding is None:
            logger.warning("No face detected in the uploaded image.")
            return Response(
                {"error": "No face detected in the image."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        face_logger.info("Face detected, calculating similarity.")
        new_embedding = np.array(new_embedding).reshape(1, -1)
        stored_embeddings = np.array(face_mask.mask_encoding)

        if stored_embeddings.ndim == 1:
            stored_embeddings = stored_embeddings.reshape(1, -1)

        similarities = cosine_similarity(new_embedding, stored_embeddings)[0]
        max_similarity = np.max(similarities)

        threshold = settings.FACE_RECOGNITION_THRESHOLD
        verified = max_similarity >= threshold

        face_logger.info(
            f"Verification completed for PIN {staff_pin}. Score: {max_similarity}, Verified: {verified}"
        )
        return Response(
            {"verified": verified, "score": float(max_similarity)},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        face_logger.error(
            f"Error during face verification for PIN {staff_pin}: {str(e)}"
        )
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="post",
    auto_schema=FormOnlySwaggerAutoSchema,  # type: ignore[reportArgumentType]
    operation_summary="Распознавание лиц",
    operation_description="Распознает лица сотрудников на изображении. Требует передачи заголовка X-API-KEY для просмотра в Swagger.",
    tags=["Face Recognition - Recognize"],
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=True,
            description="API ключ для доступа к этому эндпоинту. Без этого ключа эндпоинт скрыт в Swagger.",
        ),
        openapi.Parameter(
            name="image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Изображение с лицами для распознавания (PNG, JPG, JPEG).",
        ),
    ],
    request_body=no_body,
    responses={
        200: openapi.Response(
            description="Результат распознавания",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "recognized_staff": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT),
                        description="Список распознанных сотрудников.",
                    ),
                    "unknown_faces": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT),
                        description="Список нераспознанных лиц.",
                    ),
                },
            ),
        ),
        400: "Bad Request: Неверные данные запроса.",
        404: "Not Found: Лица не распознаны.",
        500: "Internal Server Error: Ошибка при распознавании.",
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def recognize_faces(request):
    recognize_logger = logging.getLogger("django")
    recognize_logger.info("Received request to recognize faces.")

    staff_image = request.FILES.get("image")

    if not staff_image:
        recognize_logger.warning("No image provided in the request.")
        return Response(
            {"error": "Image is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    if not staff_image.name.lower().endswith((".png", ".jpg", ".jpeg")):
        recognize_logger.warning("Invalid image format provided.")
        return Response(
            {"error": "Invalid image format. Only PNG, JPG, and JPEG are allowed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if staff_image.size == 0:
        recognize_logger.warning("Uploaded image is empty.")
        return Response(
            {"error": "Uploaded image is empty."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        recognized_staff, unknown_faces = ml.recognize_faces_in_image(staff_image)

        if not recognized_staff and not unknown_faces:
            logger.info("No staff members or unknown faces recognized.")
            return Response(
                {"error": "No staff members recognized."},
                status=status.HTTP_404_NOT_FOUND,
            )

        recognize_logger.info(
            f"Recognition completed. Recognized staff: {len(recognized_staff)}, Unknown faces: {len(unknown_faces)}."
        )
        return Response(
            {"recognized_staff": recognized_staff, "unknown_faces": unknown_faces},
            status=status.HTTP_200_OK,
        )

    except ValidationError as ve:
        recognize_logger.warning(f"Validation error during face recognition: {str(ve)}")
        return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        recognize_logger.error(f"Unexpected error during face recognition: {str(e)}")
        return Response(
            {"error": f"Face recognition error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class AbsentReasonView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrAPIKey]
    authentication_classes = [JWTAuthentication]

    def get_date_interval(self, request):
        """
        Извлекает интервал дат из параметров запроса или подставляет интервал за последнюю неделю.

        Параметры запроса:
          - start_date (str, опционально): Дата начала в формате "YYYY-MM-DD".
          - end_date (str, опционально): Дата окончания в формате "YYYY-MM-DD".

        Возвращает:
          tuple(datetime.date, datetime.date): Кортеж (query_start, query_end).

        Генерирует:
          ValueError: Если передан неверный формат даты.
        """
        today = datetime.datetime.today().date()
        default_start = today - datetime.timedelta(days=7)
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if start_date_str:
            try:
                query_start = datetime.datetime.strptime(
                    start_date_str, "%Y-%m-%d"
                ).date()
            except ValueError as e:
                logger.error(f"Неверный формат start_date: {start_date_str}")
                raise ValueError(
                    "Неверный формат start_date. Ожидается YYYY-MM-DD."
                ) from e
        else:
            query_start = default_start

        if end_date_str:
            try:
                query_end = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError as e:
                logger.error(f"Неверный формат end_date: {end_date_str}")
                raise ValueError(
                    "Неверный формат end_date. Ожидается YYYY-MM-DD."
                ) from e
        else:
            query_end = today

        return query_start, query_end

    @swagger_auto_schema(
        operation_summary="Получение записей отсутствия",
        operation_description=(
            "Метод возвращает записи отсутствия с возможностью фильтрации по интервалу дат и сотруднику.\n\n"
            "Параметры запроса:\n"
            " - **start_date** (опционально): Дата начала (формат YYYY-MM-DD).\n"
            " - **end_date** (опционально): Дата окончания (формат YYYY-MM-DD).\n"
            " - **staffs_all** (опционально): Если true, возвращаются записи для всех сотрудников, сгруппированные по сотрудникам.\n"
            " - **staff_pin** (обязательно, если staffs_all не true): PIN сотрудника для фильтрации записей.\n"
            " - **download** (опционально): Если true, возвращается ZIP-архив документов.\n"
            "\nПри параметре **download=true** архив формируется с файлами, имена которых имеют формат:\n"
            "   `staff.pin_fio_absenceID.ext` (например: `001_Ivanov_Ivan_7.pdf`)."
        ),
        tags=["Absence"],
        manual_parameters=[
            openapi.Parameter(
                name="X-API-KEY",
                in_=openapi.IN_HEADER,
                type=openapi.TYPE_STRING,
                required=False,
                description="API ключ для аутентификации (альтернатива JWT токену).",
            ),
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Дата начала (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="Дата окончания (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "staffs_all",
                openapi.IN_QUERY,
                description="Если true, возвращаются записи для всех сотрудников, сгруппированные по сотрудникам",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "staff_pin",
                openapi.IN_QUERY,
                description="PIN сотрудника (обязательный, если staffs_all не true)",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "download",
                openapi.IN_QUERY,
                description="Если true, возвращается ZIP-архив документов",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: openapi.Response(
                description=(
                    "При успешном выполнении возвращается:\n"
                    " - Если download=true, ZIP-архив документов.\n"
                    " - Если staffs_all=true, сгруппированные данные по сотрудникам.\n"
                    " - Иначе – список записей отсутствия для указанного сотрудника."
                )
            ),
            400: openapi.Response(description="Ошибка в параметрах запроса"),
        },
    )
    def get(self, request, *args, **kwargs):
        """
        **GET** запрос для получения записей отсутствия.

        **Параметры запроса:**
          - **start_date** (опционально): Дата начала (формат YYYY-MM-DD).
          - **end_date** (опционально): Дата окончания (формат YYYY-MM-DD).
          - **staffs_all** (опционально): Если true, возвращаются записи для всех сотрудников.
          - **staff_pin** (обязательно, если staffs_all не true): PIN сотрудника.
          - **download** (опционально): Если true, возвращается ZIP-архив документов.

        **Ответ:**
          - **HTTP 200 OK**: JSON с записями отсутствия или сгруппированными данными по сотрудникам, либо ZIP-архив.
          - **HTTP 400 BAD REQUEST**: При отсутствии обязательных параметров или неверном формате даты.
        """
        staffs_all = request.query_params.get("staffs_all", "").lower() == "true"
        staff_pin = request.query_params.get("staff_pin")

        if not staffs_all and not staff_pin:
            logger.warning("Не передан обязательный параметр 'staff_pin'.")
            return Response(
                {"error": "Параметр 'staff_pin' обязателен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            query_start, query_end = self.get_date_interval(request)
        except ValueError as e:
            logger.error(f"Ошибка при разборе интервала дат: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        absences = models.AbsentReason.objects.filter(
            end_date__gte=query_start,
            start_date__lte=query_end,
        )

        if not staffs_all:
            absences = absences.filter(staff__pin=staff_pin)

        download = request.query_params.get("download", "").lower() == "true"
        if download:
            in_memory = BytesIO()
            with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
                for absence in absences:
                    if absence.document:
                        file_path = absence.document.path
                        if os.path.exists(file_path):
                            _, ext = os.path.splitext(file_path)
                            ext = ext.lower()
                            staff = absence.staff
                            fio = f"{staff.surname}_{staff.name}"
                            new_filename = f"{staff.pin}_{fio}_{absence.id}{ext}"
                            zf.write(file_path, arcname=new_filename)
            in_memory.seek(0)
            logger.info(
                f"Возвращается ZIP-архив документов за период {query_start} - {query_end}."
            )
            response = HttpResponse(
                in_memory.getvalue(), content_type="application/zip"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="documents_{query_start}_{query_end}.zip"'
            )
            return response

        if not staffs_all:
            serializer_context = {"minimal_staff": True}
            serializer = serializers.AbsentReasonSerializer(
                absences, many=True, context=serializer_context
            )
            logger.info(
                f"Возвращается список записей отсутствия для staff_pin: {staff_pin}. Количество записей: {len(absences)}."
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        grouped = {}
        for absence in absences:
            staff = absence.staff
            key = staff.pin
            if key not in grouped:
                grouped[key] = {
                    "staff": {"pin": staff.pin, "fio": f"{staff.surname} {staff.name}"},
                    "absences": [],
                }
            absence_data = serializers.AbsentReasonSerializer(
                absence, context={"minimal_staff": True}
            ).data
            grouped[key]["absences"].append(absence_data)
        result = list(grouped.values())
        logger.info(
            f"Возвращается сгруппированный список записей отсутствия для всех сотрудников. Количество групп: {len(result)}."
        )
        return Response(result, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary="Создание записи отсутствия",
        operation_description=(
            "Метод создает новую запись отсутствия.\n\n"
            "Тело запроса должно содержать следующие поля:\n"
            " - **staff** (строка): PIN сотрудника.\n"
            " - **reason** (строка): Код причины отсутствия (например, `sick_leave`).\n"
            '   Если передано некорректное значение, по умолчанию устанавливается `other` (отображается как "Другая причина").\n'
            " - **start_date** (строка): Дата начала (формат YYYY-MM-DD).\n"
            " - **end_date** (строка): Дата окончания (формат YYYY-MM-DD).\n"
            " - **approved** (bool): Статус утверждения.\n"
            " - **document** (файл, опционально): Прикрепленный документ. Разрешенные форматы: pdf, jpg, jpeg, png."
        ),
        tags=["Absence"],
        request_body=serializers.AbsentReasonSerializer,
        responses={
            201: openapi.Response(description="Запись отсутствия успешно создана."),
            400: openapi.Response(description="Неверные входные данные"),
        },
    )
    def post(self, request, *args, **kwargs):
        """
        **POST** запрос для создания новой записи отсутствия.

        **Тело запроса:**
          - **staff** (строка): PIN сотрудника.
          - **reason** (строка): Код причины отсутствия (например, `sick_leave` или `other`).
          - **start_date** (строка): Дата начала (формат YYYY-MM-DD).
          - **end_date** (строка): Дата окончания (формат YYYY-MM-DD).
          - **approved** (bool): Статус утверждения.
          - **document** (файл, опционально): Прикрепленный документ. Допустимые расширения: pdf, jpg, jpeg, png.

        **Ответ:**
          - **HTTP 201 CREATED**: Сообщение об успешном создании записи.
          - **HTTP 400 BAD REQUEST**: Если входные данные неверны.
        """
        if not request.user.is_authenticated:
            logger.warning(
                "Пользователь не аутентифицирован для POST /api/absent_staff/"
            )
            return Response(
                {"error": "Требуется аутентификация"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = serializers.AbsentReasonSerializer(data=request.data)

        if serializer.is_valid():
            try:
                instance = serializer.save()
                logger.info(
                    f"Запись отсутствия создана. ID: {instance.id}, "
                    f"Сотрудник: {instance.staff.pin if hasattr(instance, 'staff') and hasattr(instance.staff, 'pin') else 'N/A'}, "
                    f"Период: {instance.start_date} - {instance.end_date}"
                )
                return Response(
                    {"message": "Запись отсутствия успешно создана."},
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                logger.error(
                    f"Ошибка при сохранении записи отсутствия: {str(e)}", exc_info=True
                )
                return Response(
                    {"error": f"Ошибка при сохранении: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            logger.warning(f"Ошибка валидации данных: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
