from django.urls import path
from drf_yasg import openapi
from rest_framework import permissions
from drf_yasg.views import get_schema_view


class IsAuthenticatedOrReadOnly(permissions.BasePermission):
    """
    The request is authenticated as a user, or is a read-only request.
    """

    def has_permission(self, request, view):
        return (
            request.method in permissions.SAFE_METHODS
            or request.user
            and request.user.is_authenticated
        )


schema_view = get_schema_view(
    openapi.Info(
        title="API",
        default_version="v1",
        description="API для управления системой мониторинга",
        contact=openapi.Contact(email="ekozlov00@mail.ru"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(IsAuthenticatedOrReadOnly,),
)

urlpatterns = [
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
]
