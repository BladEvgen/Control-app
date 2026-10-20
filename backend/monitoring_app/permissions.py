import logging

from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from monitoring_app import models

logger = logging.getLogger("monitoring_app.permissions")


class IsAuthenticatedOrAPIKey(BasePermission):

    def has_permission(self, request, view):
        path = request.path_info
        method = request.method

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
        except Exception as e:
            logger.warning(
                "Unexpected error during JWT authentication for %s %s: %s", method, path, e
            )

        api_key = request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
        if api_key:
            try:
                key_obj = models.APIKey.objects.get(key=api_key)
                if key_obj.is_active:
                    return True
            except models.APIKey.DoesNotExist:
                pass
            except Exception as e:
                logger.warning("Error checking API key for %s %s: %s", method, path, e)

        logger.warning(
            "Permission denied for %s %s. User authenticated: %s",
            method,
            path,
            request.user.is_authenticated if hasattr(request.user, "is_authenticated") else False,
        )
        return False


class IsStaffToken(BasePermission):
    """Только запросы с токеном сотрудника (StaffJWTAuthentication), не админки и не ключа."""

    def has_permission(self, request, view):
        from monitoring_app.authentication import StaffPrincipal

        return isinstance(request.user, StaffPrincipal)
