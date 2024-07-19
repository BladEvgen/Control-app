import os
import zipfile
import datetime
from tempfile import NamedTemporaryFile
from concurrent.futures import ThreadPoolExecutor

from drf_yasg import openapi
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from openpyxl import load_workbook
from django.core.cache import caches
from django.http import HttpResponse
from django.db.models import Count, Q
from django.views.generic import View
from rest_framework.views import APIView
from django.contrib.auth.models import User
from rest_framework.response import Response
from django.core.files.base import ContentFile
from drf_yasg.utils import swagger_auto_schema
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

from monitoring_app import models, serializers, utils


class StaffAttendancePagination(PageNumberPagination):
    page_size = 5000
    page_size_query_param = "page_size"
    max_page_size = 20000


Cache = caches["default"]


def get_cache(
    key: str, query: callable = lambda: any, timeout: int = 10, cache: any = Cache
) -> any:
    """
    Получает данные из кэша по указанному ключу `key`.

    Args:
        key (str): Строковый ключ для доступа к данным в кэше.
        query (callable, optional): Функция, вызываемая для получения данных в случае их отсутствия в кэше.
            По умолчанию используется `lambda: any`, возвращающая всегда `True`.
        timeout (int, optional): Время жизни данных в кэше в секундах. По умолчанию: 10 секунд.
        cache (any, optional): Объект кэша, используемый для хранения данных. По умолчанию: `Cache`.

    Returns:
        any: Возвращает данные из кэша, если они есть, иначе данные, полученные из запроса.

    Examples:
        >>> get_cache("my_data_key")
    """
    data = cache.get(key)
    if data is None:
        data = query()
        cache.set(key, data, timeout)
    return data


@permission_classes([AllowAny])
def home(request):
    return render(
        request,
        "index.html",
    )


@permission_classes([AllowAny])
def react_app(request):
    return render(request, "index.html")


class StaffAttendanceStatsView(APIView):
    permission_classes = [IsAuthenticated]
    """
    View для получения статистики о посещаемости персонала.

    Фильтрация:
    - Учитываются только сотрудники, относящиеся к подотделу с ID 4958.

    Параметры:
    - запрос: объект HttpRequest

    Returns:
    - Объект ответа, содержащий статистику посещаемости персонала.

    Usage:
    Это представление принимает запросы GET с дополнительными параметрами запроса:
    - дата: дата в формате «ГГГГ-ММ-ДД». По умолчанию используется текущая дата.
    - PIN-код: PIN-код персонала для получения статистики по конкретному сотруднику.

    Если пин-код не указан, возвращается общая статистика, включая общее количество сотрудников,
    текущее количество сотрудников, количество отсутствующих сотрудников и присутствие сотрудников с 8:00 до 18:00.
    Если указан PIN-код, возвращается статистика для конкретного сотрудника.

    Данные ответа включают в себя:
    - Для общей статистики:
    - total_staff_count: общее количество сотрудников.
    - present_staff_count: количество присутствующих сотрудников.
    - absent_staff_count: количество отсутствующих сотрудников.
    - present_between_9_to_18: количество сотрудников, присутствующих с 8:00 до 18:00.
    - present_data: список словарей, содержащих информацию о нынешнем персонале.
    - absent_data: список словарей, содержащих информацию об отсутствующем персонале.
    
    - Для статистики отдельных сотрудников:
    - Present_data: список словарей, содержащих информацию о нынешнем персонале.
    - absent_data: список словарей, содержащих информацию об отсутствующем персонале.
    """

    @swagger_auto_schema(
        operation_summary="Получить список людей об их присутствии",
        operation_description="View для получения статистики о посещаемости персонала.",
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
                                    "staff_pin": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "name": openapi.Schema(type=openapi.TYPE_STRING),
                                },
                            ),
                        ),
                    },
                ),
            ),
            404: "Not Found",
            500: "Internal Server Error",
        },
        manual_parameters=[
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
        date_param = request.query_params.get(
            "date", timezone.now().date().strftime("%Y-%m-%d")
        )

        date_param = datetime.datetime.strptime(date_param, "%Y-%m-%d").date()
        next_date = date_param + datetime.timedelta(days=1)
        pin_param = request.query_params.get("pin", None)

        cache_key = f"staff_attendance_stats_{date_param}_{pin_param}"

        def query():
            try:
                department = models.ChildDepartment.objects.filter(id=4958).first()
                department_name = (
                    department.name if department else "Unknown Department"
                )

                staff_queryset = models.Staff.objects.filter(
                    department__parent_id=4958
                ).select_related("department")

                staff_attendance_queryset = models.StaffAttendance.objects.filter(
                    date_at__gte=date_param,
                    date_at__lt=next_date,
                    staff__in=staff_queryset,
                ).select_related("staff")

                if not staff_attendance_queryset.exists():
                    return {
                        "department_name": department_name,
                        "total_staff_count": 0,
                        "present_staff_count": 0,
                        "absent_staff_count": 0,
                        "present_between_9_to_18": 0,
                        "present_data": [],
                        "absent_data": [],
                    }

                total_staff_count = staff_queryset.count()

                present_staff = staff_attendance_queryset.exclude(first_in__isnull=True)
                present_staff_pins = set(
                    present_staff.values_list("staff__pin", flat=True)
                )
                absent_staff_count = total_staff_count - len(present_staff_pins)

                present_between_9_to_18 = present_staff.filter(
                    first_in__time__range=["08:00", "19:00"]
                ).count()

                present_data = []
                absent_data = []

                for staff in staff_queryset:
                    if staff.pin in present_staff_pins:
                        attendance = present_staff.get(staff__pin=staff.pin)
                        total_minutes = 8 * 60
                        minutes_present = (
                            (attendance.last_out - attendance.first_in).total_seconds()
                            / 60
                            if attendance.last_out
                            else 0
                        )
                        individual_percentage = (minutes_present / total_minutes) * 100
                        present_data.append(
                            {
                                "staff_pin": staff.pin,
                                "name": f"{staff.surname} {staff.name}",
                                "minutes_present": round(minutes_present, 2),
                                "individual_percentage": round(
                                    individual_percentage, 2
                                ),
                            }
                        )
                    else:
                        absent_data.append(
                            {
                                "staff_pin": staff.pin,
                                "name": f"{staff.surname} {staff.name}",
                            }
                        )

                if pin_param:
                    present_data = [
                        entry
                        for entry in present_data
                        if entry["staff_pin"] == pin_param
                    ]
                    absent_data = [
                        entry
                        for entry in absent_data
                        if entry["staff_pin"] == pin_param
                    ]

                    response_data = {
                        "department_name": department_name,
                        "present_data": present_data,
                        "absent_data": absent_data,
                    }
                else:
                    response_data = {
                        "department_name": department_name,
                        "total_staff_count": total_staff_count,
                        "present_staff_count": len(present_data),
                        "absent_staff_count": absent_staff_count,
                        "present_between_9_to_18": present_between_9_to_18,
                        "present_data": present_data,
                        "absent_data": absent_data,
                    }

                return response_data
            except Exception as e:
                return {"error": str(e)}

        cached_data = get_cache(
            cache_key, query=query, timeout=6 * 60 * 60, cache=Cache
        )

        return Response(cached_data)


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить ID всех родительских департаментов",
    operation_description="Метод для получения списка всех родительских департаментов.",
    responses={
        200: openapi.Response(
            description="Успешный запрос. Возвращается список ID родительских департаментов.",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="ID родительского департамента.",
                ),
            ),
        ),
        404: openapi.Response(
            description="Не удалось найти департаменты",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
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
    try:
        parent_departments = models.ParentDepartment.objects.all()
        parent_ids = [department.id for department in parent_departments]
        return Response(data=parent_ids, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(data={"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="GET",
    operation_summary="Сводная информация о департаменте",
    operation_description="Метод для получения сводной информации о департаменте и его дочерних подразделениях с количеством сотрудников.",
    responses={
        200: openapi.Response(
            description="Успешный запрос. Возвращается сводная информация о департаменте и его дочерних подразделениях.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "name": openapi.Schema(
                        type=openapi.TYPE_STRING, description="Название департамента."
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
                                    type=openapi.TYPE_INTEGER,
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
                                    type=openapi.TYPE_INTEGER,
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

    if not models.ChildDepartment.objects.filter(id=parent_department_id).exists():
        return Response(
            status=status.HTTP_404_NOT_FOUND,
            data={"message": f"Department with ID {parent_department_id} not found"},
        )
    try:

        def calculate_staff_count(department):
            child_departments = models.ChildDepartment.objects.filter(parent=department)
            staff_count = (
                child_departments.aggregate(total_staff=Count("staff"))["total_staff"]
                or 0
            )

            for child_dept in child_departments:
                staff_count += calculate_staff_count(child_dept)

            return staff_count

        parent_department = get_object_or_404(
            models.ChildDepartment, id=parent_department_id
        )

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

        cached_data = get_cache(
            cache_key, query=lambda: data, timeout=1 * 10, cache=Cache
        )

        return Response(cached_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(data={"message": str(e)}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="get",
    operation_summary="Получить описание подотдела",
    operation_description="Получите подробную информацию о подотделе и его сотрудниках.",
    manual_parameters=[
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
                                type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME
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
    try:
        child_department = models.ChildDepartment.objects.get(id=child_department_id)
    except models.ChildDepartment.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    all_departments = [child_department] + child_department.get_all_child_departments()
    staff_in_department = models.Staff.objects.filter(department__in=all_departments)

    staff_data = {}
    for staff_member in staff_in_department:
        if staff_member.surname == "Нет фамилии":
            fio = staff_member.name
        else:
            fio = f"{staff_member.surname} {staff_member.name}"

        staff_data[staff_member.pin] = {
            "FIO": fio,
            "date_of_creation": staff_member.date_of_creation,
            "avatar": staff_member.avatar.url if staff_member.avatar else None,
            "positions": [position.name for position in staff_member.positions.all()],
        }

    sorted_staff_data = dict(
        sorted(staff_data.items(), key=lambda item: item[1]["FIO"])
    )

    data = {
        "child_department": serializers.ChildDepartmentSerializer(
            child_department
        ).data,
        "staff_count": staff_in_department.count(),
        "staff_data": sorted_staff_data,
    }

    return Response(data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить информации об сотруднике",
    operation_description="Получение подробной информации о сотруднике, включая данные о посещаемости, заработной плате и типе контракта",
    manual_parameters=[
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
                        type=openapi.TYPE_STRING, description="Имя сотрудника"
                    ),
                    "surname": openapi.Schema(
                        type=openapi.TYPE_STRING, description="Фамилия сотрудника"
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
                        additional_properties=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            description="Данные о посещаемости",
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
                },
            ),
        ),
        400: "Неверный запрос, дата начала не может быть позже даты окончания",
        404: "Сотрудник не найден",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_detail(request, staff_pin):
    """
    Эндпоинт для получения подробной информации о сотруднике,
    включая данные о посещаемости и заработной плате.

    **Запрос (GET):**

    * **URL:** `/staff/<staff_pin>/`
    * **Параметры:**
        * `staff_pin` (обязательный, строка): Уникальный идентификатор сотрудника (PIN).
        * `start_date` (необязательный, строка): Дата начала периода для фильтрации данных о посещаемости
          (формат: YYYY-MM-DD). По умолчанию - за последние 7 дней.
        * `end_date` (необязательный, строка): Дата окончания периода для фильтрации данных о посещаемости
          (формат: YYYY-MM-DD). По умолчанию - текущая дата.

    **Ответ (JSON):**

    * **Код 200:**
        * `name` (строка): Имя сотрудника.
        * `surname` (строка): Фамилия сотрудника.
        * `positions` (список строк): Список должностей сотрудника.
        * `avatar` (строка, формат URI): URL аватара сотрудника (может быть null).
        * `department` (строка): Отдел, к которому относится сотрудник.
        * `department_id` (число): Id отдела.
        * `attendance` (объект): Данные о посещаемости за указанный период.
            Ключи - даты посещаемости в формате "DD-MM-YYYY", значения - объекты:
                * `first_in` (строка, формат ЧЧ:ММ DD-MM-YYYY): Время первого входа (может быть null).
                * `last_out` (строка, формат ЧЧ:ММ DD-MM-YYYY): Время последнего выхода (может быть null).
                * `percent_day` (число): Процент отработанного времени за день.
                * `total_minutes` (число): Общее количество отработанных минут за день.
        * `percent_for_period` (число): Общий процент работы за указанный период.
        * `salary` (число): Общая заработная плата сотрудника (может быть null).
        * `contract_type` (строка): Тип контракта сотрудника.

    * **Код 400:** Неверный запрос, дата начала не может быть позже даты окончания.
    * **Код 404:** Сотрудник не найден.
    """

    def fetch_staff_data():
        try:
            staff = models.Staff.objects.get(pin=staff_pin)
        except models.Staff.DoesNotExist:
            return None
        return staff

    staff = get_cache(f"staff_{staff_pin}", query=fetch_staff_data, timeout=1 * 10)

    if staff is None:
        return Response(status=status.HTTP_404_NOT_FOUND)

    end_date_str = request.query_params.get(
        "end_date", timezone.now().strftime("%Y-%m-%d")
    )
    start_date_str = request.query_params.get(
        "start_date", (timezone.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    )

    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")

    if start_date > end_date:
        return Response(
            data={"error": "start_date cannot be greater than end_date"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cache_key = f"staff_detail_{staff_pin}_{start_date_str}_{end_date_str}"

    def get_staff_detail():
        staff_attendance = models.StaffAttendance.objects.filter(
            staff=staff, date_at__range=[start_date, end_date]
        )
        public_holidays = models.PublicHoliday.objects.filter(
            date__range=[start_date, end_date]
        ).values_list("date", "is_working_day")

        holiday_dict = {
            date: is_working_day for date, is_working_day in public_holidays
        }

        attendance_data = {}
        total_minutes_for_period = 0
        total_days_with_data = 0
        percent_for_period = 0

        for attendance in staff_attendance:
            date_at = attendance.date_at - datetime.timedelta(days=1)
            is_weekend = date_at.weekday() >= 5
            is_holiday = date_at in holiday_dict
            is_off_day = (is_weekend and date_at not in holiday_dict) or (
                is_holiday and not holiday_dict[date_at]
            )

            first_in = attendance.first_in
            last_out = attendance.last_out

            if first_in is None or last_out is None:
                percent_day = 0
                total_minutes_worked = 0
            else:
                total_minutes_expected = 8 * 60
                total_minutes_worked = (last_out - first_in).total_seconds() / 60
                total_minutes_for_period += total_minutes_worked
                total_days_with_data += 1

                percent_day = (total_minutes_worked / total_minutes_expected) * 100

            attendance_entry = {
                "first_in": first_in if first_in else None,
                "last_out": last_out if last_out else None,
                "percent_day": round(percent_day, 2),
                "total_minutes": (
                    round(total_minutes_worked, 2) if first_in and last_out else 0
                ),
                "is_weekend": is_off_day,
            }

            if is_off_day and total_minutes_worked > 0:
                percent_for_period += percent_day * 1.5
            elif not is_off_day and total_minutes_worked == 0:
                percent_for_period -= 25
            else:
                percent_for_period += percent_day

            attendance_data[date_at.strftime("%d-%m-%Y")] = attendance_entry

        if total_days_with_data > 0:
            percent_for_period /= total_days_with_data

        salaries = models.Salary.objects.filter(staff=staff)
        total_salary = salaries.first().total_salary if salaries.exists() else None
        avatar_url = staff.avatar.url if staff.avatar else "/media/images/no-avatar.png"
        contract_type = salaries.first().contract_type if salaries.exists() else None

        data = {
            "name": staff.name,
            "surname": staff.surname if staff.surname != "Нет фамилии" else "",
            "positions": [position.name for position in staff.positions.all()],
            "avatar": avatar_url,
            "department": staff.department.name if staff.department else "N/A",
            "department_id": staff.department.id if staff.department else "N/A",
            "attendance": attendance_data,
            "percent_for_period": round(percent_for_period, 2),
            "contract_type": contract_type,
            "salary": total_salary,
        }

        return data

    data = get_cache(cache_key, query=get_staff_detail, timeout=1 * 10)

    return Response(data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="get",
    operation_summary="Посещаемость сотрудников по отделу ",
    operation_description="Получить данные о посещаемости сотрудников по ID подразделения",
    responses={
        200: openapi.Response(
            description="Успешный ответ",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "department_name": openapi.Schema(
                        type=openapi.TYPE_STRING, description="Название подразделения"
                    ),
                    "attendance": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "date": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            "staff_fio": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                description="ФИО сотрудника",
                                            ),
                                            "first_in": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                format=openapi.FORMAT_DATETIME,
                                                description="Время первого входа сотрудника",
                                            ),
                                            "last_out": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                format=openapi.FORMAT_DATETIME,
                                                description="Время последнего выхода сотрудника",
                                            ),
                                        },
                                    ),
                                    description="Список сотрудников и их посещаемость за дату",
                                )
                            },
                        ),
                        description="Список посещаемости по датам",
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description="Ошибка в запросе",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
        404: openapi.Response(
            description="Не найдено",
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
    manual_parameters=[
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

    Возвращаемые данные:
    - department_name: Название подразделения.
    - attendance: Список посещаемости сотрудников, сгруппированных по датам.

    Пример ответа:
    {
        "department_name": "отдел цифровизации образовательных технологий",
        "attendance": [
            {
                "2024-07-01": [
                    {
                        "staff_fio": "Testov Test",
                        "first_in": "2024-07-01T00:00:00+05:00",
                        "last_out": "2024-07-01T23:59:59+05:00"
                    },
                    ...
                ]
            },
            ...
        ]
    }

    Возможные ошибки:
    - 400: Не указаны параметры начала или конца периода.
    - 404: Подразделение не найдено или данные о посещаемости не найдены.
    - 500: Внутренняя ошибка сервера.
    """
    try:
        end_date_str = request.query_params.get("end_date")
        start_date_str = request.query_params.get("start_date")
        page = request.query_params.get("page", 1)

        if not end_date_str or not start_date_str:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Не указаны параметры начала или конца периода"},
            )

        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

        if start_date > end_date:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Дата начала не может быть больше даты конца"},
            )

        try:
            department = models.ChildDepartment.objects.get(id=department_id)
        except models.ChildDepartment.DoesNotExist:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={"error": "Подразделение не найдено"},
            )

        def get_all_child_department_ids(department_id):
            child_ids = models.ChildDepartment.objects.filter(
                Q(parent_id=department_id) | Q(parent__parent_id=department_id)
            ).values_list("id", flat=True)
            return list(child_ids)

        department_ids = [department_id] + get_all_child_department_ids(department_id)

        cache_key = (
            f"staff_detail_{department_id}_{start_date_str}_{end_date_str}_page_{page}"
        )

        def query():
            staff_attendance = (
                models.StaffAttendance.objects.filter(
                    staff__department_id__in=department_ids,
                    date_at__range=(start_date, end_date),
                )
                .select_related("staff")
                .order_by("date_at", "staff__surname", "staff__name")
            )

            paginator = StaffAttendancePagination()
            result_page = paginator.paginate_queryset(staff_attendance, request)
            serializer = serializers.StaffAttendanceByDateSerializer(
                result_page, many=True, context={"department_name": department.name}
            )

            return paginator.get_paginated_response(serializer.data).data

        cached_data = get_cache(cache_key, query=query, timeout=3600)
        return Response(cached_data)

    except Exception as e:
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data={"error": str(e)},
        )


@swagger_auto_schema(
    method="post",
    operation_summary="Зарегистрировать нового пользователя (доступно только для администратора)",
    operation_description="Регистрирует нового пользователя в системе. Разрешено только для администратора.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["username", "password"],
        properties={
            "username": openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Желаемое имя для нового пользователя",
            ),
            "password": openapi.Schema(
                type=openapi.TYPE_STRING, description="Пароль для нового пользователя"
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
                        type=openapi.TYPE_STRING, description="Описание ошибки запроса"
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

    username = request.data.get("username", None)
    password = request.data.get("password", None)
    if not username or not password:
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"message": "Требуется юзернейм и пароль"},
        )

    if not utils.password_check(password):
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"messgae": "Пароль не прошел требования"},
        )
    user, created = User.objects.get_or_create(username=username)
    if not created:
        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data={"message": "Данный username уже занят"},
        )

    user.set_password(password)
    user.save()
    return Response(
        status=status.HTTP_201_CREATED, data={"message": "пользователь успешно создан"}
    )


@swagger_auto_schema(
    method="get",
    operation_summary="Получить профиль пользователя",
    operation_description="Получить профиль текущего аутентифицированного пользователя.",
    responses={
        200: openapi.Response(
            description="Данные профиля пользователя",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "is_banned": openapi.Schema(
                        type=openapi.TYPE_BOOLEAN, description="Забанен ли пользователь"
                    ),
                    "user": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "username": openapi.Schema(
                                type=openapi.TYPE_STRING, description="Имя пользователя"
                            ),
                            "email": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                format=openapi.FORMAT_EMAIL,
                                description="Электронная почта",
                            ),
                            "first_name": openapi.Schema(
                                type=openapi.TYPE_STRING, description="Имя"
                            ),
                            "last_name": openapi.Schema(
                                type=openapi.TYPE_STRING, description="Фамилия"
                            ),
                            "is_staff": openapi.Schema(
                                type=openapi.TYPE_BOOLEAN,
                                description="Является ли пользователь сотрудником",
                            ),
                            "date_joined": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                format=openapi.FORMAT_DATETIME,
                                description="Дата регистрации",
                            ),
                            "last_login": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                format=openapi.FORMAT_DATETIME,
                                description="Дата последнего входа",
                            ),
                            "phonenumber": openapi.Schema(
                                type=openapi.TYPE_STRING, description="Номер телефона"
                            ),
                        },
                    ),
                },
            ),
        ),
        401: openapi.Response(
            description="Unauthorized: Если пользователь не аутентифицирован.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "detail": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Сообщение об ошибке аутентификации",
                    )
                },
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_profile_detail(request):
    """
    Получить профиль текущего аутентифицированного пользователя.

    Этот метод возвращает профиль текущего аутентифицированного пользователя, включая его основные данные и информацию о последнем входе.

    Аргументы:
    - request: объект запроса.

    Возвращаемые данные:
    - Ответ с данными профиля пользователя, включая флаги is_banned, user (с username, email, first_name, last_name, is_staff, date_joined, last_login, phonenumber).

    Возможные ошибки:
    - 401: Если пользователь не аутентифицирован.
    """

    def get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    user_profile = models.UserProfile.objects.get(user=request.user)
    user_profile.last_login_ip = get_client_ip(request)
    user_profile.save(update_fields=["last_login_ip"])
    serializer = serializers.UserProfileSerializer(user_profile)
    return Response(serializer.data)


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
    operation_summary="Запрос на получение данных с Внешнего сервера",
    operation_description="Запрос на получение данных о посещаемости. Требует передачи заголовка X-API-KEY для аутентификации.",
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=True,
            description="API ключ для аутентификации запроса.",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Запуск процесса получения данных.",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING, description="Статус сообщения."
                    ),
                },
            ),
        ),
        403: "Forbidden: Если доступ запрещен или отсутствует API ключ.",
        500: "Internal Server Error: В случае ошибки сервера.",
    },
)
@api_view(http_method_names=["GET"])
@permission_classes([AllowAny])
def fetch_data_view(request):
    """
    Запрос на получение данных о посещаемости. Требует передачи заголовка X-API-KEY для аутентификации.

    Args:
    запрос: объект запроса.

    Returns:
    Ответ: статус сообщения.

    Raises:
    Http403: Если доступ запрещен или отсутствует API ключ.
    Http500: В случае ошибки сервера.
    """
    try:
        api_key = request.headers.get("X-API-KEY")
        if api_key is None:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"error": "Доступ запрещен. Не указан API ключ."},
            )

        utils.get_all_attendance()
        return Response(status=status.HTTP_200_OK, data={"message": "Done"})

    except Exception as e:
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"error": str(e)}
        )


@swagger_auto_schema(
    method="get",
    operation_summary="Получение данных о посещаемости в формате Excel",
    operation_description="Получение данных о посещаемости с внешнего сервера и создание Excel файла. Требуется аутентификация.",
    manual_parameters=[
        openapi.Parameter(
            name="X-API-KEY",
            in_=openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            required=True,
            description="API ключ для аутентификации запроса.",
        ),
        openapi.Parameter(
            name="endDate",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Конечная дата для данных о посещаемости в формате YYYY-MM-DD.",
        ),
        openapi.Parameter(
            name="startDate",
            in_=openapi.IN_QUERY,
            type=openapi.TYPE_STRING,
            required=True,
            description="Начальная дата для данных о посещаемости в формате YYYY-MM-DD.",
        ),
    ],
    responses={
        200: openapi.Response(
            description="Excel файл с данными о посещаемости.",
            schema=openapi.Schema(
                type=openapi.TYPE_FILE,
                description="Созданный Excel файл, содержащий данные о посещаемости.",
            ),
        ),
        400: openapi.Response(
            description="Bad Request: отсутствует начальная или конечная дата."
        ),
        403: openapi.Response(
            description="Forbidden: если доступ запрещен или отсутствует API ключ."
        ),
        500: openapi.Response(
            description="Internal server error: если сервер столкнулся с ошибкой."
        ),
    },
)
@api_view(http_method_names=["GET"])
@permission_classes([IsAuthenticated])
def sent_excel(request, department_id):
    """
    Получение данных о посещаемости в формате Excel.

    Получение данных о посещаемости с внешнего сервера на основе предоставленного ID отдела,
    начальной и конечной дат. Создание и возврат Excel файла, содержащего данные о посещаемости.

    Аргументы:
        request (HttpRequest): Объект HTTP запроса.
        department_id (int): ID отдела, для которого запрашиваются данные о посещаемости.

    Параметры запроса:
        - startDate (str): Начальная дата для данных о посещаемости в формате YYYY-MM-DD.
        - endDate (str): Конечная дата для данных о посещаемости в формате YYYY-MM-DD.

    Возвращает:
        HttpResponse: HTTP ответ с созданным Excel файлом или сообщением об ошибке.

    Исключения:
        ValueError: Если начальная или конечная дата отсутствует в параметрах запроса.
        ConnectionError: Если возникла проблема с получением данных с внешнего сервера.
    """

    end_date = request.query_params.get("endDate", None)
    start_date = request.query_params.get("startDate", None)

    if not all([end_date, start_date]):
        return Response(
            {"error": "Missing startDate or endDate"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError as e:
        return Response(
            {"error": f"Invalid date format: {e}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    end_date += datetime.timedelta(days=1)
    start_date += datetime.timedelta(days=1)

    main_ip = settings.MAIN_IP
    rows = []
    page = 1

    while True:
        cache_key = f"{main_ip}_api_department_stats_{department_id}_{start_date}_{end_date}_page_{page}"
        url = f"{main_ip}/api/department/stats/{department_id}/?end_date={end_date}&start_date={start_date}&page={page}"

        data = get_cache(cache_key, query=lambda: utils.fetch_data(url), timeout=3600)

        if "results" not in data or not data["results"]:
            break

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(utils.parse_attendance_data, data["results"])
            rows += future.result()

        if not data.get("next"):
            break
        page += 1

    if rows:
        df_pivot_sorted = utils.create_dataframe(rows)

        wb = utils.save_to_excel(df_pivot_sorted)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f"attachment; filename=Посещаемость_{department_id}.xlsx"
        )

        with NamedTemporaryFile(delete=False) as tmp:
            wb.save(tmp.name)
            tmp.seek(0)
            response.write(tmp.read())

        return response
    else:
        return Response(
            {"error": "Failed to generate Excel file"},
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
            с контекстом, содержащим список всех категорий файлов (categories).
        """

        categories = models.FileCategory.objects.all()
        context = {"categories": categories}
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

        file_path = request.FILES.get("file")
        category_slug = request.POST.get("category")

        if file_path and category_slug:
            try:
                if file_path.name.endswith(".xlsx"):
                    self.handle_excel(file_path, category_slug)
                elif file_path.name.endswith(".zip") and category_slug == "photo":
                    self.handle_zip(file_path)
                else:
                    context = {"error": "Неверный формат файла или категория"}
                    return render(request, self.template_name, context=context)

                return redirect("uploadFile")
            except Exception as error:
                context = {"error": f"Ошибка при обработке файла: {str(error)}"}
        else:
            context = {
                "error": "Проверьте правильность заполненных данных или неверный формат файла"
            }

        return render(request, self.template_name, context=context)

    @transaction.atomic
    def handle_excel(self, file_path, category_slug):
        """
        Обрабатывает загрузку и импорт данных из файла Excel.

        Args:
            file_path (File): Путь к загруженному файлу.
            category_slug (str): Категория файла для обработки.

        Raises:
            Exception: Если произошла ошибка при обработке файла Excel.
        """

        wb = load_workbook(file_path)
        ws = wb.active
        ws.delete_rows(1, 2)
        rows = list(ws.iter_rows())
        rows.sort(key=lambda row: row[0].value, reverse=False)

        if category_slug == "departments":
            self.process_departments(rows)
        elif category_slug == "staff":
            self.process_staff(rows)

    def process_departments(self, rows):
        """
        Обрабатывает данные для категории "departments" из Excel файла.

        Args:
            rows (list): Список строк из файла Excel.

        Raises:
            Exception: Если произошла ошибка при обработке строки.
        """

        for row in rows:
            try:
                parent_department_id = int(row[2].value)
                parent_department_name = row[3].value
                child_department_name = row[1].value
                child_department_id = int(row[0].value)

                if child_department_id == 1:
                    continue

                parent_department = None
                if parent_department_name:
                    parent_department, created = (
                        models.ParentDepartment.objects.get_or_create(
                            id=parent_department_id,
                            defaults={"name": parent_department_name},
                        )
                    )

                    parent_department_as_child, created = (
                        models.ChildDepartment.objects.get_or_create(
                            id=parent_department.id,
                            defaults={
                                "name": parent_department.name,
                                "parent": None,
                            },
                        )
                    )

                else:
                    parent_department_as_child = models.ChildDepartment.objects.get(
                        id=1
                    )

                child_department, created = (
                    models.ChildDepartment.objects.get_or_create(
                        id=child_department_id,
                        defaults={
                            "name": child_department_name,
                            "parent": parent_department_as_child,
                        },
                    )
                )

            except Exception as error:
                print(f"Ошибка при обработке строки: {str(error)}")

    def process_staff(self, rows):
        """
        Обрабатывает данные для категории "staff" из Excel файла.

        Args:
            rows (list): Список строк из файла Excel.

        Raises:
            Exception: Если произошла ошибка при обработке строки.
        """

        staff_instances = []
        departments_cache = {}

        for row in rows:
            pin = row[0].value
            name = row[1].value
            surname = row[2].value or "Нет фамилии"
            department_id = int(row[3].value)
            position_name = row[5].value or "Сотрудник"

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
                department = None  # Default department value

            staff_instance = models.Staff(
                pin=pin,
                name=name,
                surname=surname,
                department=department,
            )

            staff_instances.append(staff_instance)

        pin_list = [staff.pin for staff in staff_instances]
        existing_staff = models.Staff.objects.filter(pin__in=pin_list)
        existing_staff_dict = {staff.pin: staff for staff in existing_staff}

        staff_to_create = []
        staff_to_update = []

        for staff_instance in staff_instances:
            if staff_instance.pin in existing_staff_dict:
                existing = existing_staff_dict[staff_instance.pin]
                existing.name = staff_instance.name
                existing.surname = staff_instance.surname
                existing.department = staff_instance.department
                staff_to_update.append(existing)
            else:
                staff_to_create.append(staff_instance)

        if staff_to_create:
            models.Staff.objects.bulk_create(staff_to_create)

        for staff in staff_to_update:
            staff.save()

    def handle_zip(self, file_path):
        """
        Обрабатывает загрузку и импорт данных из ZIP архива.

        Args:
            file_path (File): Путь к загруженному файлу.

        Raises:
            Exception: Если произошла ошибка при обработке ZIP файла.
        """
        with zipfile.ZipFile(file_path, "r") as zip_file:
            zip_file.extractall("/tmp")
            for filename in zip_file.namelist():
                pin = os.path.splitext(filename)[0]
                staff_member = models.Staff.objects.filter(pin=pin).first()
                if staff_member:
                    with zip_file.open(filename) as file:
                        staff_member.avatar.save(
                            filename, ContentFile(file.read()), save=False
                        )
                        staff_member.save()


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
                            type=openapi.TYPE_STRING, description="Сообщение об ошибке."
                        ),
                        "error": openapi.Schema(
                            type=openapi.TYPE_STRING, description="Описание ошибки."
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
        api_key = request.headers.get("X-API-KEY")

        if not api_key:
            return Response(
                {"message": "API Key is missing"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            secret_key = utils.APIKeyUtility.get_secret_key()
            data = utils.APIKeyUtility.decrypt_data(
                api_key, secret_key, fields=("created_at", "is_active")
            )
            return Response({"data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"message": "Invalid API Key", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
