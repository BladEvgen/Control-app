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
            logger.warning(f"Unexpected error during JWT authentication for {method} {path}: {str(e)}")

        api_key = request.headers.get("X-API-KEY") or request.headers.get("x-api-key")
        if api_key:
            try:
                key_obj = models.APIKey.objects.get(key=api_key)
                if key_obj.is_active:
                    return True
            except models.APIKey.DoesNotExist:
                pass
            except Exception as e:
                logger.warning(f"Error checking API key for {method} {path}: {str(e)}")

        logger.warning(
            f"Permission denied for {method} {path}. "
            f"User authenticated: {request.user.is_authenticated if hasattr(request.user, 'is_authenticated') else False}"
        )
        return False
