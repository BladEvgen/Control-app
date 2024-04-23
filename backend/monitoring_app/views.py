import os
import random
import zipfile
import datetime

from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.core.files.base import ContentFile
from django.contrib.auth import authenticate, login, logout
from django.views.generic import (
    View,
)
from rest_framework import status
from openpyxl import load_workbook
from django.core.cache import caches
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from monitoring_app import models, utils

Cache = caches["default"]


def get_cache(
    key: str, query: callable = lambda: any, timeout: int = 10, cache: any = Cache
) -> any:
    data = cache.get(key)
    if data is None:
        data = query()
        cache.set(key, data, timeout)
    return data


def home(request):
    return render(request, "home.html", context={})


class StaffAttendanceStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_param = request.query_params.get(
            "date", datetime.datetime.now().date().strftime("%Y-%m-%d")
        )
        pin_param = request.query_params.get("pin", None)

        cache_key = f"staff_attendance_stats_{date_param}_{pin_param}"

        def query():
            try:
                staff_attendance = models.StaffAttendance.objects.filter(
                    date_at=date_param
                )
                total_staff_count = models.Staff.objects.count()
                present_staff = staff_attendance.exclude(first_in__isnull=True)
                absent_staff_count = total_staff_count - present_staff.count()

                present_between_8_to_18 = present_staff.filter(
                    first_in__time__range=["8:00", "18:00"]
                ).count()

                present_data = []
                absent_data = []
                for attendance in present_staff:
                    total_minutes = 8 * 60
                    minutes_present = (
                        (attendance.last_out - attendance.first_in).total_seconds() / 60
                        if attendance.last_out
                        else 0
                    )
                    individual_percentage = (minutes_present / total_minutes) * 100
                    if minutes_present < 1:
                        absent_data.append(
                            {
                                "staff_pin": attendance.staff.pin,
                                "name": f"{attendance.staff.surname} {attendance.staff.name}",
                            }
                        )
                    else:
                        present_data.append(
                            {
                                "staff_pin": attendance.staff.pin,
                                "name": f"{attendance.staff.surname} {attendance.staff.name}",
                                "minutes_present": round(minutes_present, 2),
                                "individual_percentage": round(
                                    individual_percentage, 2
                                ),
                            }
                        )

                for attendance in staff_attendance.filter(first_in__isnull=True):
                    absent_data.append(
                        {
                            "staff_pin": attendance.staff.pin,
                            "name": f"{attendance.staff.surname} {attendance.staff.name}",
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
                        "present_data": present_data,
                        "absent_data": absent_data,
                    }
                else:
                    response_data = {
                        "total_staff_count": total_staff_count,
                        "present_staff_count": len(present_data),
                        "absent_staff_count": absent_staff_count,
                        "present_between_8_to_18": present_between_8_to_18,
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


def logout_view(request):
    logout(request)
    return redirect("login")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("uploadFile")

    return render(request, "login.html", context={})


class UploadFileView(View):
    template_name = "upload_file.html"

    def get(self, request, *args, **kwargs):
        categories = models.FileCategory.objects.all()
        context = {"categories": categories}
        return render(request, self.template_name, context=context)

    def post(self, request, *args, **kwargs):
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
                            surname = row[2].value
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
