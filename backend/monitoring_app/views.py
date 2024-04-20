from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login, logout
from django.views.generic import (
    View,
)
from rest_framework import status
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.decorators import api_view, permission_classes

from monitoring_app import models, utils


@api_view(http_method_names=["GET"])
@permission_classes([AllowAny])
def home(request):
    return Response(data={"message": "ok"}, status=status.HTTP_200_OK)


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
                                    id=parent_department_id, name=parent_department_name
                                )
                            )

                            child_department = models.ChildDepartment.objects.create(
                                id=child_department_id,
                                name=child_department_name,
                                parent=parent_department,
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

            except Exception as error:
                context = {"error": f"Ошибка при обработке файла: {str(error)}"}
        else:
            context = {
                "error": "Проверьте правильность заполненных данных, или неверный формат файла"
            }

        return render(request, self.template_name, context=context)
