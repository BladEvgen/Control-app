from __future__ import annotations

from typing import Any, cast

from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError


class SessionAuthenticationAllowTokenOrApiKey(SessionAuthentication):
    """
    Session auth with CSRF, but gracefully skips itself for requests that
    explicitly use JWT Bearer or X-API-KEY auth.

    Why:
    - We keep SessionAuthentication globally for places that need it.
    - We avoid CSRF 403 on endpoints where frontend sends Bearer/API key.
    """

    def _has_bearer_or_api_key(self, request: Any) -> bool:
        authorization = str(request.META.get("HTTP_AUTHORIZATION", "") or "")
        if authorization.lower().startswith("bearer "):
            return True
        api_key = request.META.get("HTTP_X_API_KEY")
        return bool(api_key)

    def authenticate(self, request: Any):
        if self._has_bearer_or_api_key(request):
            return None
        return super().authenticate(request)


class StaffPrincipal:
    """request.user для запросов с токеном сотрудника (не учётная запись Django)."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, staff):
        self.staff = staff


class StaffJWTAuthentication(BaseAuthentication):
    """``Authorization: Bearer <staff_access>`` → StaffPrincipal. Архивный — отказ."""

    def authenticate(self, request):
        from monitoring_app import models
        from monitoring_app.custom_jwt import STAFF_ID_CLAIM, StaffAccessToken

        parts = request.META.get("HTTP_AUTHORIZATION", "").split()
        if len(parts) != 2 or parts[0] != "Bearer":
            return None
        try:
            token = StaffAccessToken(cast(Any, parts[1]))
        except TokenError as exc:
            raise AuthenticationFailed(f"Токен сотрудника недействителен: {exc}") from None
        staff = models.Staff.objects.filter(id=token.get(STAFF_ID_CLAIM)).first()
        if staff is None:
            raise AuthenticationFailed("Сотрудник недоступен")
        return StaffPrincipal(staff), token

    def authenticate_header(self, request):
        _ = request
        return 'Bearer realm="staff"'
