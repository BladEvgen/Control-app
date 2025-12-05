from django.urls import path
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from monitoring_app import models


class DynamicSchemeGenerator(OpenAPISchemaGenerator):
    """
    Кастомный генератор схемы, который динамически определяет схему (http/https)
    на основе текущего запроса. Поддерживает определение схемы за прокси через заголовок X-Forwarded-Proto.
    """

    def get_schema(self, request=None, public=False):
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
    """
    Разрешает доступ к Swagger UI по JWT, API ключу или сессии (Django admin/собственная аутентификация).
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            auth_result = jwt_authenticator.authenticate(request)
            if auth_result is not None:
                user, token = auth_result
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
    """
    Разрешает доступ к JSON схеме по JWT, API ключу или сессии.
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            auth_result = jwt_authenticator.authenticate(request)
            if auth_result is not None:
                user, token = auth_result
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


schema_view_ui = get_schema_view(
    openapi.Info(
        title="API",
        default_version="v1",
        description="API для управления системой мониторинга",
        contact=openapi.Contact(email="ekozlov00@mail.ru"),
        license=openapi.License(name="MIT License"),
    ),
    public=False,
    permission_classes=(SwaggerUIAccessPermission,),
    url=None,
    urlconf="django_settings.urls",
    patterns=None,
    generator_class=DynamicSchemeGenerator,
)

schema_view_json = get_schema_view(
    openapi.Info(
        title="API",
        default_version="v1",
        description="API для управления системой мониторинга",
        contact=openapi.Contact(email="ekozlov00@mail.ru"),
        license=openapi.License(name="MIT License"),
    ),
    public=False,
    permission_classes=(SchemaAccessPermission,),
    url=None,
    urlconf="django_settings.urls",
    patterns=None,
    generator_class=DynamicSchemeGenerator,
)

urlpatterns = [
    path(
        "swagger/",
        schema_view_ui.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path(
        "redoc/", schema_view_ui.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
    path(
        "swagger<format>/",
        schema_view_json.without_ui(cache_timeout=0),
        name="schema-json",
    ),
]
