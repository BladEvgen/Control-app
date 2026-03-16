from __future__ import annotations

from typing import Any

from rest_framework.authentication import SessionAuthentication


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

