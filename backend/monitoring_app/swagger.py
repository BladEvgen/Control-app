from django.urls import path, re_path
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from monitoring_app import models
from monitoring_app.swagger_views import swagger_json_with_login, swagger_ui_with_login


class DynamicSchemeGenerator(OpenAPISchemaGenerator):
    """Кастомный генератор схемы OpenAPI для Swagger документации.

    Генератор динамически определяет схему (http/https) на основе текущего запроса.
    Поддерживает определение схемы за прокси через заголовок X-Forwarded-Proto.
    Скрывает эндпоинты распознавания лиц, если не передан X-API-KEY.
    Если массив face_recognition_paths пустой, ничего не скрывается.

    Attributes:
        request: Текущий HTTP запрос, используется для проверки заголовков.
    """

    def __init__(self, *args, **kwargs):
        """Инициализирует генератор схемы.

        Args:
            *args: Позиционные аргументы для родительского класса.
            **kwargs: Именованные аргументы для родительского класса.
        """
        super().__init__(*args, **kwargs)
        self.request = None

    def should_include_endpoint(self, endpoint_path, method, view, public):
        """Определяет, должен ли эндпоинт быть включен в схему.

        Скрывает эндпоинты распознавания лиц, если не передан X-API-KEY.
        Если массив face_recognition_paths пустой, ничего не скрывается.

        Args:
            endpoint_path (str): Путь эндпоинта (переименован из path для избежания конфликта).
            method (str): HTTP метод запроса.
            view: View класс или функция.
            public (bool): Флаг публичного доступа.

        Returns:
            bool: True если эндпоинт должен быть включен, False иначе.
        """
        if not super().should_include_endpoint(endpoint_path, method, view, public):
            return False

        face_recognition_paths = ["/verify-face/", "/recognize-faces/"]

        if not face_recognition_paths:
            return True

        is_face_recognition = any(
            face_path in endpoint_path for face_path in face_recognition_paths
        )

        if is_face_recognition:
            if hasattr(self, "request") and self.request:
                api_key = None
                for key in self.request.META.keys():
                    if key.upper() == "HTTP_X_API_KEY":
                        api_key = self.request.META[key]
                        break

                if not api_key:
                    api_key = getattr(self.request, "headers", {}).get("X-API-KEY") or getattr(
                        self.request, "headers", {}
                    ).get("x-api-key")

                if not api_key:
                    return False

        return True

    def get_schema(self, request=None, public=False):
        """Генерирует OpenAPI схему с динамическим определением протокола.

        Args:
            request: HTTP запрос для определения схемы.
            public (bool): Флаг публичного доступа.

        Returns:
            openapi.Spec: Сгенерированная OpenAPI схема.
        """
        self.request = request

        schema = super().get_schema(request=request, public=public)
        if request and schema:
            forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "").lower()
            if forwarded_proto in ("https", "http"):
                scheme = forwarded_proto
            else:
                scheme = "https" if request.is_secure() else "http"

            if hasattr(schema, "schemes"):
                if scheme not in schema.schemes:
                    schema.schemes = [scheme]
            else:
                schema.schemes = [scheme]
        return schema


class SwaggerUIAccessPermission(permissions.BasePermission):
    """Разрешает доступ к Swagger UI по JWT, API ключу или сессии.

    Поддерживает следующие способы аутентификации:
    - Django сессия (Django admin/собственная аутентификация)
    - JWT токен (Bearer token)
    - API ключ (X-API-KEY заголовок)
    """

    def has_permission(self, request, view):
        """Проверяет наличие прав доступа к Swagger UI.

        Args:
            request: HTTP запрос.
            view: View класс или функция.

        Returns:
            bool: True если доступ разрешен, False иначе.
        """
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            auth_result = jwt_authenticator.authenticate(request)
            if auth_result is not None:
                _, token = auth_result
                if token.payload.get("token_type") == "access":
                    return True
        except (InvalidToken, AuthenticationFailed):
            pass

        api_key = request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
        if api_key:
            try:
                key_obj = models.APIKey.objects.get(key=api_key)
                if key_obj.is_active:
                    return True
            except models.APIKey.DoesNotExist:
                pass

        return False


class SchemaAccessPermission(permissions.BasePermission):
    """Разрешает доступ к JSON схеме по JWT, API ключу или сессии.

    Поддерживает следующие способы аутентификации:
    - Django сессия
    - JWT токен (Bearer token)
    - API ключ (X-API-KEY заголовок)
    """

    def has_permission(self, request, view):
        """Проверяет наличие прав доступа к JSON схеме.

        Args:
            request: HTTP запрос.
            view: View класс или функция.

        Returns:
            bool: True если доступ разрешен, False иначе.
        """
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            auth_result = jwt_authenticator.authenticate(request)
            if auth_result is not None:
                _, token = auth_result
                if token.payload.get("token_type") == "access":
                    return True
        except (InvalidToken, AuthenticationFailed):
            pass

        api_key = request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
        if api_key:
            try:
                key_obj = models.APIKey.objects.get(key=api_key)
                if key_obj.is_active:
                    return True
            except models.APIKey.DoesNotExist:
                pass

        return False


class SchemaViewCache:
    """Кэш для schema view, используется для избежания циклических импортов."""

    def __init__(self):
        """Инициализирует кэш."""
        self._cache = None

    def get(self):
        """Получает кэшированный schema view или создает новый.

        Returns:
            SchemaView: Экземпляр schema view.
        """
        if self._cache is None:
            self._cache = self._create_schema_view()
        return self._cache

    def _create_schema_view(self):
        """Создает новый экземпляр schema view.

        Returns:
            SchemaView: Новый экземпляр schema view.
        """
        from monitoring_app import urls as monitoring_urls

        patterns = [
            pattern
            for pattern in monitoring_urls.urlpatterns
            if not any(
                "swagger" in str(pattern.pattern) or "redoc" in str(pattern.pattern)
                for _ in [pattern]
            )
        ]
        return get_schema_view(
            openapi.Info(
                title="API",
                default_version="v1",
                description="API для управления системой мониторинга",
                contact=openapi.Contact(email="ekozlov00@mail.ru"),
                license=openapi.License(name="MIT License"),
            ),
            public=True,
            permission_classes=(),
            patterns=patterns,
            generator_class=DynamicSchemeGenerator,
        )


_schema_view_cache = SchemaViewCache()


def _get_schema_view():
    """Ленивая загрузка schema view для избежания циклических импортов.

    Returns:
        SchemaView: Кэшированный экземпляр schema view.
    """
    return _schema_view_cache.get()


class LazySchemaView:
    """Обертка для отложенного создания schema_view до первого доступа.

    Позволяет избежать циклических импортов и создает schema_view только
    при первом обращении.
    """

    def with_ui(self, ui, _cache_timeout=0):
        """Откладывает вызов with_ui для lazy schema view с формой логина.

        Args:
            ui (str): Тип UI интерфейса ('swagger' или 'redoc').
            _cache_timeout (int): Таймаут кэша (не используется, для совместимости).

        Returns:
            function: View функция для отображения Swagger/ReDoc UI.
        """

        def view(request, *args, **kwargs):
            schema_view_instance = _get_schema_view()
            return swagger_ui_with_login(request, schema_view_instance, ui=ui)

        return view

    def without_ui(self, _cache_timeout=0):
        """Откладывает вызов without_ui для lazy schema view с проверкой авторизации.

        Args:
            _cache_timeout (int): Таймаут кэша (не используется, для совместимости).

        Returns:
            function: View функция для получения JSON/YAML схемы.
        """

        def view(request, *args, **kwargs):
            schema_view_instance = _get_schema_view()
            format_param = kwargs.get("format")
            return swagger_json_with_login(request, schema_view_instance, format_param=format_param)

        return view


schema_view = LazySchemaView()

urlpatterns = [
    path(
        "swagger/",
        schema_view.with_ui("swagger", _cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", _cache_timeout=0), name="schema-redoc"),
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(_cache_timeout=0),
        name="schema-json",
    ),
]
