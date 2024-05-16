import os
import zipfile
import datetime

from django.db.models import Count
from django.core.cache import caches
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.core.files.base import ContentFile
from django.contrib.auth import authenticate, login, logout
from django.views.generic import (
    View,
)
from drf_yasg import openapi
from rest_framework import status
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

from monitoring_app import models, serializers, utils

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


class StaffAttendanceStatsView(APIView):
    permission_classes = [IsAuthenticated]
    """
    View для получения статистики о посещаемости персонала.

    Parametrs:
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
            "date", datetime.datetime.now().date().strftime("%Y-%m-%d")
        )
        pin_param = request.query_params.get("pin", None)

        cache_key: str = f"staff_attendance_stats_{date_param}_{pin_param}"

        def query():
            try:
                staff_attendance = models.StaffAttendance.objects.filter(
                    date_at=date_param
                )
                if not staff_attendance:
                    response_data = {"message": f"No data found for date {date_param}"}
                    return response_data

                total_staff_count = models.Staff.objects.count()

                present_staff = staff_attendance.exclude(first_in__isnull=True)
                present_staff_pins = present_staff.values_list("staff__pin", flat=True)
                absent_staff_count = total_staff_count - present_staff.count()

                present_between_9_to_18 = present_staff.filter(
                    first_in__time__range=["8:00", "19:00"]
                ).count()

                present_data = []
                absent_data = []

                for staff in models.Staff.objects.all():
                    if staff.pin in present_staff_pins:
                        present_data.append(
                            {
                                "staff_pin": staff.pin,
                                "name": f"{staff.surname} {staff.name}",
                                "minutes_present": 0,
                                "individual_percentage": 0,
                            }
                        )
                    else:
                        absent_data.append(
                            {
                                "staff_pin": staff.pin,
                                "name": f"{staff.surname} {staff.name}",
                            }
                        )

                for attendance in present_staff:
                    total_minutes = 8 * 60
                    minutes_present = (
                        (attendance.last_out - attendance.first_in).total_seconds() / 60
                        if attendance.last_out
                        else 0
                    )
                    individual_percentage = (minutes_present / total_minutes) * 100
                    for entry in present_data:
                        if entry["staff_pin"] == attendance.staff.pin:
                            entry["minutes_present"] = round(minutes_present, 2)
                            entry["individual_percentage"] = round(
                                individual_percentage, 2
                            )
                            break

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
                        "present_data": present_data,
                        "absent_data": absent_data,
                    }
                else:
                    response_data = {
                        "total_staff_count": total_staff_count,
                        "present_staff_count": len(present_data),
                        "absent_staff_count": absent_staff_count,
                        "present_between_9_to_18": present_between_9_to_18,
                        "present_data": present_data,
                        "absent_data": absent_data,
                    }

                return response_data
            except Exception as e:
                return Response(
                    data={"error": str(e)}, status=status.HTTP_404_NOT_FOUND
                )

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
        404: "Департаменты не найдены.",
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_parent_id(request):
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
    if not models.ParentDepartment.objects.filter(id=parent_department_id).exists():
        return Response(
            status=status.HTTP_404_NOT_FOUND,
            data={"message": f"Department with ID {parent_department_id} not found"},
        )

    def query():
        try:
            parent_department = models.ParentDepartment.objects.get(
                id=parent_department_id
            )
        except models.ParentDepartment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        def calculate_staff_count(department):
            child_departments = models.ChildDepartment.objects.filter(parent=department)
            staff_count = (
                child_departments.aggregate(total_staff=Count("staff"))["total_staff"]
                or 0
            )

            for child_dept in child_departments:
                staff_count += calculate_staff_count(child_dept.id)

            return staff_count

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

        return data

    cached_data = get_cache(cache_key, query=query, timeout=1 * 10, cache=Cache)
    return Response(cached_data, status=status.HTTP_200_OK)


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
        404: "Not Found: Если подотдела не сущестует.",
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

    staff_in_department = models.Staff.objects.filter(department=child_department)
    staff_data = {}

    for staff_member in staff_in_department:
        staff_data[staff_member.pin] = {
            "FIO": staff_member.surname + " " + staff_member.name,
            "date_of_creation": staff_member.date_of_creation,
            "avatar": staff_member.avatar.url if staff_member.avatar else None,
            "positions": [position.name for position in staff_member.positions.all()],
        }

    staff_data = dict(sorted(staff_data.items(), reverse=True))

    data = {
        "child_department": serializers.ChildDepartmentSerializer(
            child_department
        ).data,
        "staff_count": staff_in_department.count(),
        "staff_data": staff_data,
    }

    return Response(data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="GET",
    operation_summary="Получить информации об сотруднике",
    operation_description="Получение подробной информации о сотруднике, включая данные о посещаемости и заработной плате",
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
        * `staff_pin` (обязательный, строка): Уникальный идентификатор сотрудника (PIN)
        * `start_date` (необязательный, строка): Дата начала периода для фильтрации
            данных о посещаемости (формат: YYYY-MM-DD). По умолчанию - за последние 7 дней.
        * `end_date` (необязательный, строка): Дата окончания периода для фильтрации
            данных о посещаемости (формат: YYYY-MM-DD). По умолчанию - текущая дата.

    **Ответ (JSON):**

    * **Код состояния 200:**
        * `name` (строка): Имя сотрудника
        * `surname` (строка): Фамилия сотрудника
        * `positions` (список строк): Список должностей сотрудника
        * `avatar` (строка, формат URI): URL аватара сотрудника (может быть null)
        * `department` (строка): Отдел, к которому относится сотрудник
        * `department_id` (число): Id отдела
        * `attendance` (объект): Данные о посещаемости за указанный период.
            Ключи - даты посещаемости в формате "DD-MM-YYYY", значения - объекты:
                * `first_in` (строка, формат ЧЧ:ММ DD-MM-YYYY): Время первого входа (может быть null)
                * `last_out` (строка, формат ЧЧ:ММ DD-MM-YYYY): Время последнего выхода (может быть null)
                * `percent_day` (число): Процент отработанного времени за день
                * `total_minutes` (число): Общее количество отработанных минут за день
        * `percent_for_period` (число): Общий процент работы за указанный период
        * `salary` (число): Общая заработная плата сотрудника (может быть null)
    * **Код состояния 400:** Неверный запрос, дата начала не может быть позже даты окончания
    * **Код состояния 404:** Сотрудник не найден
    """
    try:
        staff = models.Staff.objects.get(pin=staff_pin)
    except models.Staff.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    end_date_str = request.query_params.get(
        "end_date", timezone.now().strftime("%Y-%m-%d")
    )
    start_date_str = request.query_params.get(
        "start_date", (timezone.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    )

    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = end_date + datetime.timedelta(days=1)
    start_date = start_date + datetime.timedelta(days=1)
    if start_date > end_date:
        return Response(
            data={"error": "start_date cannot be greater than end_date"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    staff_attendance = models.StaffAttendance.objects.filter(
        staff=staff, date_at__range=[start_date, end_date]
    )

    attendance_data = {}
    total_minutes_for_period = 0
    total_days = 0
    percent_for_period = 0
    for attendance in staff_attendance:
        date_at = attendance.date_at - datetime.timedelta(days=1)
        is_weekend = date_at.weekday() >= 5

        first_in = attendance.first_in
        last_out = attendance.last_out

        if first_in is None or last_out is None:
            percent_day = 0
        else:
            total_minutes_expected = 8 * 60
            total_minutes_worked = (last_out - first_in).total_seconds() / 60
            total_minutes_for_period += total_minutes_worked
            total_days += 1

            percent_day = (total_minutes_worked / total_minutes_expected) * 100

        attendance_entry = {
            "first_in": (first_in if first_in else None),
            "last_out": (last_out if last_out else None),
            "percent_day": round(percent_day, 2),
            "total_minutes": (
                round(total_minutes_worked, 2) if first_in and last_out else 0
            ),
            "is_weekend": is_weekend,
        }

        if date_at.weekday() >= 5:

            if attendance_entry["total_minutes"] > 60:
                percent_for_period *= 1.5
            else:
                percent_for_period += percent_day
        else:

            if attendance_entry["total_minutes"] == 0:
                percent_day *= 0.75

        total_weekend_days = 0

        for single_date in utils.daterange(start_date, end_date):
            if single_date.weekday() >= 5:
                total_weekend_days += 1
        attendance_data[date_at.strftime("%d-%m-%Y")] = attendance_entry

    total_hours_expected = ((end_date - start_date).days - total_weekend_days) * 8
    percent_for_period += (total_minutes_for_period / (total_hours_expected * 60)) * 100

    salaries = models.Salary.objects.filter(staff=staff)
    total_salary = salaries.first().total_salary if salaries.exists() else None
    avatar_url = staff.avatar.url if staff.avatar else "/media/images/no-avatar.png"

    data = {
        "name": staff.name,
        "surname": staff.surname,
        "positions": [position.name for position in staff.positions.all()],
        "avatar": avatar_url,
        "department": staff.department.name if staff.department else "N/A",
        "department_id": staff.department.id if staff.department else "N/A",
        "attendance": attendance_data,
        "percent_for_period": round(percent_for_period, 2),
        "salary": total_salary,
    }

    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
def staff_detail_by_department_id(request, department_id):
    try:
        end_date_str = request.query_params.get(
            "end_date", timezone.now().strftime("%Y-%m-%d")
        )
        start_date_str = request.query_params.get(
            "start_date",
            (timezone.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d"),
        )

        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

        if start_date > end_date:
            return Response(
                data={"error": "start_date cannot be greater than end_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staff_attendance = models.StaffAttendance.objects.filter(
            staff__department_id=department_id,
            date_at__gte=start_date,
            date_at__lte=end_date,
        ).order_by("staff__surname", "staff__name", "date_at")

        serializer = serializers.StaffAttendanceDetailSerializer(
            staff_attendance, many=True
        )

        return Response(serializer.data)

    except Exception as e:
        return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": str(e)})


@swagger_auto_schema(
    method="post",
    operation_summary="Зарегистрировать нового пользователя доступно только isAdmin",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["username", "password"],
        properties={
            "username": openapi.Schema(type=openapi.TYPE_STRING),
            "password": openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={
        201: "Created - Пользователь успешно зарегистрирован",
        400: openapi.Response(
            description="Bad Request - Ошибка в запросе",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
    },
    operation_description="Регистрирует нового пользователя в системе. Разрешено только для администратора.",
)
@api_view(http_method_names=["POST"])
@permission_classes([IsAdminUser])
def user_register(request):
    """
    Регистрирует нового пользователя в системе. Разрешено только для администратора.

    Этот view ожидает запрос POST, содержащий в теле запроса следующие данные:

    - имя пользователя (str): желаемое имя для нового пользователя.
    - пароль (str): пароль для нового пользователя.
        Пароль должен соответствовать требованиям системы к сложности пароля.
        которые проверяются с помощью функции `utils.password_check`.

    Ответ:

    - Ответ JSON со следующей структурой:
    - status (int): код состояния HTTP:
    - 201 Создано: Если пользователь успешно зарегистрирован.
    - ошибка 400, неверный запрос:
    - Если имя пользователя или пароль отсутствуют.
    - Если пароль не проходит проверку сложности.
    - Если имя пользователя уже занято.
    - message (str): сообщение, читаемое человеком.
    с указанием результатов процесса регистрации.

    Исключения:

    — Стандартные исключения Django, если во время создания или сохранения пользователя возникают какие-либо ошибки.
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_profile_detail(request):
    user_profile = models.UserProfile.objects.get(user=request.user)
    serializer = serializers.UserProfileSerializer(user_profile)
    return Response(serializer.data)


def logout_view(request):
    logout(request)
    return redirect("home")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("uploadFile")

    return render(request, "login.html", context={})


@api_view(["GET"])
def fetch_data_view(request):

    try:
        fetch_data = request.GET.get("fetch_data", "").lower()
        if fetch_data == "true":
            utils.get_all_attendance()
            return Response(status=status.HTTP_200_OK, data={"message": "Started"})
        else:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"error": "Access denied."},
            )
    except Exception as e:
        return Response(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"error": str(e)}
        )


class UploadFileView(View):
    """
    Класс представления для обработки действий по загрузке файлов.

    Отображает форму загрузки файла (`upload_file.html`)
    и обрабатывает POST-запросы для импорта данных из файла.
    """

    template_name = "upload_file.html"

    def get(self, request, *args, **kwargs):
        """
        Обрабатывает GET-запросы.

        Retunrs:
            HttpResponse: Отрисовывает шаблон `upload_file.html`
            с контекстом, содержащим список всех категорий файлов (`categories`).
        """

        categories = models.FileCategory.objects.all()
        context = {"categories": categories}
        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
        """
        Обрабатывает POST-запросы.

        Args:
            request (HttpRequest): Объект запроса.
            *args: Аргументы.
            **kwargs: Ключевые аргументы.

        Returns:
            HttpResponse: Возвращает редирект на страницу загрузки файла или
            рендеринг `upload_file.html` с соответствующим контекстом.

        Raises:
            Exception: Если произошла ошибка при обработке файла.
        """
        file_path = request.FILES.get("file")

        category_slug = request.POST.get("category")
        if file_path and category_slug:
            try:
                if file_path.name.endswith(".xlsx"):

                    wb = load_workbook(file_path)
                    ws = wb.active

                    ws.delete_rows(1, 2)

                    rows = list(ws.iter_rows())
                    rows.sort(key=lambda row: row[0].value, reverse=True)

                    for row in rows:
                        if category_slug == "departments":
                            try:
                                parent_department_id = int(row[2].value)
                                parent_department_name = row[3].value
                                child_department_name = row[1].value
                                child_department_id = int(row[0].value)

                                parent_department, _ = (
                                    models.ParentDepartment.objects.get_or_create(
                                        id=parent_department_id,
                                        name=parent_department_name,
                                    )
                                )

                                child_department = (
                                    models.ChildDepartment.objects.create(
                                        id=child_department_id,
                                        name=child_department_name,
                                        parent=parent_department,
                                    )
                                )

                                child_department.save()
                            except Exception as error:
                                print(f"Ошибка при обработке строки: {str(error)}")
                        elif category_slug == "staff":
                            pin = row[0].value
                            name = row[1].value
                            surname = row[2].value or "Нет фамилии"
                            department_id = int(row[3].value)
                            position_name = row[5].value

                            department = models.ChildDepartment.objects.get(
                                id=department_id
                            )

                            staff, _ = models.Staff.objects.get_or_create(
                                pin=pin,
                                defaults={
                                    "name": name,
                                    "surname": surname,
                                    "department": department,
                                },
                            )

                            position, _ = models.Position.objects.get_or_create(
                                name=position_name
                            )
                            staff.positions.add(position)
                        else:
                            context = {
                                "error": "Неизвестная категория. Пожалуйста, обратитесь к Администратору."
                            }

                    context = {"message": "Файл успешно загружен"}
                    return redirect("uploadFile")

                elif file_path.name.endswith(".zip") and category_slug == "photo":
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
                            else:
                                continue
                    return redirect("uploadFile")

            except Exception as error:
                context = {"error": f"Ошибка при обработке файла: {str(error)}"}
        else:
            context = {
                "error": "Проверьте правильность заполненных данных, или неверный формат файла"
            }

        return render(request, self.template_name, context=context)
