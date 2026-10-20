"""Password reset API used by the React pages ``/app/password-reset[/<token>]``.

The endpoints are anonymous and run without authentication classes: DRF only
enforces CSRF inside ``SessionAuthentication``, and there is no ambient
credential to forge here. The secret is the 64-char emailed token; brute force
is capped by throttling and the 1-hour token lifetime.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from monitoring_app import models, utils

GENERIC_SENT = "Если такой пользователь есть, письмо со ссылкой уже отправлено на его почту."
TOKEN_TTL = timedelta(hours=1)


class ResetThrottle(AnonRateThrottle):
    scope = "password_reset"
    rate = "20/hour"


_MESSAGE = openapi.Schema(
    type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)}
)
_ERROR = openapi.Schema(
    type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)}
)
_GONE = openapi.Response("Ссылка недействительна, устарела или уже использована", _ERROR)


def _live_tokens():
    return models.PasswordResetToken.objects.filter(
        _used=False, created_at__gt=timezone.now() - TOKEN_TTL
    )


@swagger_auto_schema(
    method="post",
    operation_summary="Запросить ссылку для сброса пароля",
    operation_description="Без авторизации и CSRF. Ответ одинаковый для существующих и "
    "несуществующих логинов; повторное письмо тому же пользователю с того же IP — не чаще "
    "раза в 5 минут. Лимит: 20 запросов в час с IP.",
    tags=["Authentication"],
    security=[],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["identifier"],
        properties={
            "identifier": openapi.Schema(type=openapi.TYPE_STRING, description="Логин или e-mail")
        },
    ),
    responses={200: _MESSAGE, 400: _ERROR, 429: "Слишком много запросов"},
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ResetThrottle])
def password_reset_request(request: Request) -> Response:
    """Email a reset link. The answer never says whether the account exists."""
    identifier = str(request.data.get("identifier") or "").strip()
    if not identifier:
        return Response({"error": "Введите логин или почту."}, status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.filter(Q(username=identifier) | Q(email__iexact=identifier)).first()
    if user and user.email:
        ip_address = utils.get_client_ip(request)
        if models.PasswordResetRequestLog.can_request_again(user, ip_address):
            utils.send_password_reset_email(user, request)
            models.PasswordResetRequestLog.log_request(user, ip_address)
    return Response({"message": GENERIC_SENT})


@swagger_auto_schema(
    method="get",
    operation_summary="Проверить ссылку сброса пароля",
    tags=["Authentication"],
    security=[],
    responses={
        200: openapi.Response(
            "Ссылка действует",
            examples={
                "application/json": {"username": "ivanov.i", "expiresAt": "2026-10-17T05:00:00Z"}
            },
        ),
        410: _GONE,
    },
)
@swagger_auto_schema(
    method="post",
    operation_summary="Установить новый пароль по ссылке",
    operation_description="Пароль: минимум 8 символов, A–Z, a–z, цифра и символ #?!@$%^&*-. "
    "После успеха ссылка и все прочие активные ссылки пользователя гаснут.",
    tags=["Authentication"],
    security=[],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["password"],
        properties={
            "password": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD)
        },
    ),
    responses={200: _MESSAGE, 400: _ERROR, 410: _GONE},
)
@api_view(["GET", "POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ResetThrottle])
def password_reset_confirm(request: Request, token: str) -> Response:
    """GET: is the link still valid. POST {password}: set it and burn the token."""
    reset = _live_tokens().select_related("user").filter(token=token).first()
    if reset is None:
        return Response(
            {"error": "Ссылка недействительна или устарела. Запросите новую."},
            status=status.HTTP_410_GONE,
        )
    if request.method == "GET":
        return Response(
            {"username": reset.user.username, "expiresAt": reset.created_at + TOKEN_TTL}
        )

    password = str(request.data.get("password") or "")
    if not utils.password_check(password):
        return Response(
            {
                "error": "Пароль не подходит: минимум 8 символов, A–Z, a–z, цифра и символ #?!@$%^&*-."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not _live_tokens().filter(pk=reset.pk).update(_used=True):
        return Response({"error": "Ссылка уже использована."}, status=status.HTTP_410_GONE)
    user = reset.user
    user.set_password(password)
    user.save(update_fields=["password"])
    _live_tokens().filter(user=user).update(_used=True)
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)
    return Response({"message": "Пароль изменён. Войдите с новым паролем."})
