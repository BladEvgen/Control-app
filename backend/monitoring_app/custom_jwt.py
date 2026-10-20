import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, cast

from django.conf import settings
from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import exceptions
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from monitoring_app import models

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


SESSION_START_CLAIM = "session_start"


def _enforce_session_max_age(raw_refresh: Any) -> None:
    """Сессия живёт не дольше JWT_SESSION_MAX_HOURS с момента входа, сколько ни ротируй.

    Просроченный refresh сразу отзывается (blacklist), повторно его не предъявить.
    """
    if not raw_refresh:
        return
    try:
        token = RefreshToken(raw_refresh)
    except TokenError:
        return
    started = int(token.get(SESSION_START_CLAIM) or token.get("iat") or 0)
    if time.time() - started > settings.JWT_SESSION_MAX_HOURS * 3600:
        token.blacklist()
        raise InvalidToken("Сессия истекла: войдите заново.")


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom serializer for obtaining JWT tokens with precise expiration times in UTC.

    Token serializers don't use create/update methods, only validate.

    Returns:
        dict: {
            "access": <access token>,
            "refresh": <refresh token>,
            "access_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
            "refresh_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
            "user": {
                "username": <username>,
                "is_banned": <bool>,
                "is_staff": <bool>,
                "is_super": <bool>
            }
        }
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token[SESSION_START_CLAIM] = int(time.time())
        return token

    def validate(self, attrs):
        data = cast(Dict[str, Any], super().validate(attrs))
        if self.user is None:
            raise exceptions.AuthenticationFailed("User is not authenticated")
        user = cast("AbstractUser", self.user)
        token = RefreshToken(data["refresh"])
        access_exp_seconds = float(token.access_token["exp"])
        refresh_exp_seconds = float(token["exp"])
        access_exp = datetime.fromtimestamp(access_exp_seconds, tz=timezone.utc)
        refresh_exp = datetime.fromtimestamp(refresh_exp_seconds, tz=timezone.utc)
        data["access_token_expires"] = access_exp.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        data["refresh_token_expires"] = refresh_exp.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        try:
            user_profile = models.UserProfile.objects.get(user=user)
            user_data = {
                "username": user.username,
                "is_banned": user_profile.is_banned,
                "is_staff": user.is_staff,
                "is_super": user.is_superuser,
            }
        except models.UserProfile.DoesNotExist:
            user_data = {"username": user.username, "is_banned": False}
        data["user"] = user_data
        return data


@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        operation_summary="Получение JWT токенов доступа",
        operation_description=(
            "Получает пару JWT токенов (access и refresh) для аутентификации. "
            "Требует username и password. Возвращает токены с точным временем истечения в UTC."
        ),
        tags=["Authentication"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["username", "password"],
            properties={
                "username": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Имя пользователя",
                    example="admin",
                ),
                "password": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description="Пароль пользователя",
                    example="password123",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Успешная аутентификация",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "access": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="JWT access токен",
                        ),
                        "refresh": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="JWT refresh токен",
                        ),
                        "access_token_expires": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_DATETIME,
                            description="Время истечения access токена в формате ISO 8601 UTC",
                        ),
                        "refresh_token_expires": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_DATETIME,
                            description="Время истечения refresh токена в формате ISO 8601 UTC",
                        ),
                        "user": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "username": openapi.Schema(type=openapi.TYPE_STRING),
                                "is_banned": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                "is_super": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            },
                        ),
                    },
                ),
            ),
            401: openapi.Response(
                description="Неверные учетные данные",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "detail": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Сообщение об ошибке аутентификации",
                        ),
                    },
                ),
            ),
        },
    ),
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom view for obtaining JWT tokens using CustomTokenObtainPairSerializer.
    """

    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Custom serializer for refreshing JWT tokens with precise expiration times in UTC.

    Token serializers don't use create/update methods, only validate.

    Returns:
        dict: {
            "access": <new access token>,
            "refresh": <new refresh token> (if ROTATE_REFRESH_TOKENS is True),
            "access_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
            "refresh_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
        }
    """

    def validate(self, attrs):
        _enforce_session_max_age(attrs.get("refresh"))
        data = cast(Dict[str, Any], super().validate(attrs))

        access_token_str = data.get("access")
        refresh_token_str = data.get("refresh")

        if not access_token_str:
            raise exceptions.ValidationError("Access token not found in response")

        try:
            from rest_framework_simplejwt.tokens import AccessToken

            access_token = AccessToken(access_token_str)
            access_exp_seconds = float(access_token["exp"])
            access_exp = datetime.fromtimestamp(access_exp_seconds, tz=timezone.utc)
            data["access_token_expires"] = access_exp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )

            if refresh_token_str:
                refresh_token = RefreshToken(refresh_token_str)
                refresh_exp_seconds = float(refresh_token["exp"])
                refresh_exp = datetime.fromtimestamp(refresh_exp_seconds, tz=timezone.utc)
                data["refresh_token_expires"] = refresh_exp.isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z")
            else:
                original_refresh = attrs.get("refresh")
                if original_refresh:
                    try:
                        old_refresh_token = RefreshToken(original_refresh)
                        refresh_exp_seconds = float(old_refresh_token["exp"])
                        refresh_exp = datetime.fromtimestamp(refresh_exp_seconds, tz=timezone.utc)
                        data["refresh_token_expires"] = refresh_exp.isoformat(
                            timespec="milliseconds"
                        ).replace("+00:00", "Z")
                    except Exception:
                        pass
        except Exception:
            pass

        return data


@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        operation_summary="Обновление JWT токена доступа",
        operation_description=(
            "Обновляет access токен используя refresh токен. "
            "Возвращает новый access токен (и refresh токен, если включен ROTATE_REFRESH_TOKENS) "
            "с точным временем истечения в UTC."
        ),
        tags=["Authentication"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["refresh"],
            properties={
                "refresh": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="JWT refresh токен",
                    example="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Токен успешно обновлен",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "access": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Новый JWT access токен",
                        ),
                        "refresh": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Новый JWT refresh токен (если включен ROTATE_REFRESH_TOKENS)",
                        ),
                        "access_token_expires": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_DATETIME,
                            description="Время истечения access токена в формате ISO 8601 UTC",
                        ),
                        "refresh_token_expires": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_DATETIME,
                            description="Время истечения refresh токена в формате ISO 8601 UTC",
                        ),
                    },
                ),
            ),
            401: openapi.Response(
                description="Неверный или истекший refresh токен",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "detail": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Сообщение об ошибке",
                        ),
                        "code": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Код ошибки",
                        ),
                    },
                ),
            ),
        },
    ),
)
class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom view for refreshing JWT tokens using CustomTokenRefreshSerializer.
    """

    serializer_class = CustomTokenRefreshSerializer


@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        operation_summary="Верификация JWT токена",
        operation_description=(
            "Проверяет валидность JWT токена. Возвращает статус проверки токена."
        ),
        tags=["Authentication"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["token"],
            properties={
                "token": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="JWT токен для верификации",
                    example="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Токен валиден",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={},
                ),
            ),
            401: openapi.Response(
                description="Токен невалиден или истек",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "detail": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Сообщение об ошибке",
                        ),
                        "code": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Код ошибки",
                        ),
                    },
                ),
            ),
        },
    ),
)
class CustomTokenVerifyView(TokenVerifyView):
    """
    Custom view for verifying JWT tokens.
    """


STAFF_ID_CLAIM = "staff_id"


class StaffAccessToken(AccessToken):
    token_type = "staff_access"
    lifetime = timedelta(minutes=settings.STAFF_JWT_ACCESS_MINUTES)


class StaffRefreshToken(RefreshToken):
    token_type = "staff_refresh"
    lifetime = timedelta(minutes=settings.STAFF_JWT_REFRESH_MINUTES)
    access_token_class = StaffAccessToken


def issue_staff_tokens(staff_id: int, session_start: int | None = None) -> dict:
    """Пара staff-токенов. session_start переносится при обновлении — потолок сессии общий."""
    started = int(time.time()) if session_start is None else session_start
    refresh = StaffRefreshToken()
    refresh[STAFF_ID_CLAIM] = staff_id
    refresh[SESSION_START_CLAIM] = started
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "access_expires_in": settings.STAFF_JWT_ACCESS_MINUTES * 60,
        "session_expires_at": started + settings.STAFF_JWT_SESSION_MAX_HOURS * 3600,
    }
