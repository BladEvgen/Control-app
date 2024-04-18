from drf_yasg import openapi
from rest_framework import status
from openpyxl import load_workbook
from django.contrib.auth.models import User
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated

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


@swagger_auto_schema(
    method="POST",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["file"],
        properties={
            "file": openapi.Schema(
                type=openapi.TYPE_STRING,
                format="binary",
                description="Файл XLSX для загрузки",
            )
        },
    ),
    responses={
        200: "Успешная загрузка файла",
        400: "Неверный формат файла или ошибка при обработке",
        405: "Метод не разрешен",
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_file(request):
    """
    Загружает файл XLSX, содержащий данные об отделах, и обрабатывает его.

    **Разрешения:**
        - Требуется авторизованный пользователь (класс разрешений IsAuthenticated)

    **Запрос:**
        - Метод: POST
        - Данные: Мультипарт форма данных с единственным ключом файла под названием "file", содержащим данные XLSX.

    **Ответ:**
        - При успехе (статус=200):
            - JSON-ответ с сообщением: "Файл XLSX успешно загружен!"
        - При ошибке (статус=400):
            - JSON-ответ с сообщением об ошибке, указывающим причину сбоя.
                - Возможные сообщения об ошибках:
                    - "Неверный формат файла." (Неверный формат файла)
                    - "Ошибка при обработке файла: {details исключения}" (Ошибка обработки файла)
        - При недопустимом методе (статус=405):
            - JSON-ответ с сообщением об ошибке: "Метод не разрешен." (Метод не разрешен)

    **Функциональность:**
        1. Проверяет, является ли метод запроса POST.
        2. Извлекает загруженный файл из request.FILES.get("file").
        3.  Проверяет формат файла:
            - Проверяет, соответствует ли тип контента "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" (XLSX).
        4. Обрабатывает допустимый файл XLSX:
            - Загружает книгу с помощью load_workbook.
            - Удаляет первые две строки (обязательно: в них стоят заголовки файла).
            - Сортирует оставшиеся строки по значению первого столбца в порядке убывания.
            - Перебирает отсортированные строки и обновляет значения ячеек на рабочем листе.
            - Сохраняет обновленную книгу обратно в загруженный файл.
            - Перебирает строки (начиная с 1-й, если учитывать что прошлые 2 были удалены):
                - Извлекает идентификатор, имя родительского отдела и имя дочернего отдела.
                - Использует get_or_create для эффективного создания родительских отделов, если они не существуют.
                - Создает дочерние отделы с извлеченными данными и присваивает их соответствующему родительскому отделу.
                - Сохраняет дочерний отдел.
        5. Возвращает успешный ответ с сообщением при успешной обработке.
        6. Возвращает ошибку с подробным сообщением в случае любых исключений или ошибок проверки.
    """
    if request.method == "POST":
        file = request.FILES.get("file")
        if (
            file
            and file.content_type
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            try:
                wb = load_workbook(file)
                ws = wb.active

                ws.delete_rows(1, 2)

                rows = list(ws.iter_rows())
                rows.sort(key=lambda row: row[0].value, reverse=True)

                for idx, row in enumerate(rows, start=1):
                    for col_idx, cell in enumerate(row, start=1):
                        ws.cell(row=idx, column=col_idx, value=cell.value)

                wb.save(file)

                for row in ws.iter_rows(min_row=3):
                    parent_department_id = int(row[2].value)
                    parent_department_name = row[3].value
                    child_department_name = row[1].value

                    parent_department, _ = (
                        models.ParentDepartment.objects.get_or_create(
                            id=parent_department_id, name=parent_department_name
                        )
                    )

                    child_department = models.ChildDepartment.objects.create(
                        name=child_department_name, parent=parent_department
                    )

                    child_department.save()

                return Response(
                    {"message": "Файл XLSX успешно загружен!"},
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"error": f"Ошибка при обработке файла: {e}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"error": "Неверный формат файла."}, status=status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {"error": "Метод не разрешен."}, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
