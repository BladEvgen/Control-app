import logging
from monitoring_app import models
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

logger = logging.getLogger(__name__)


class IsAuthenticatedOrAPIKey(BasePermission):

    def has_permission(self, request, view):

        logger.info("Checking permissions for request")

        if request.user and request.user.is_authenticated:
            logger.info("User is authenticated via session")
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            auth_result = jwt_authenticator.authenticate(request)
            if auth_result is not None:
                user, token = auth_result
                if token.payload.get("token_type") == "access":
                    logger.info("User authenticated via JWT")
                    return True
        except (InvalidToken, AuthenticationFailed) as e:
            logger.warning(f"JWT authentication failed: {str(e)}")

        api_key = request.headers.get("X-API-KEY")
        if api_key:
            logger.info("API key provided")
            try:
                key_obj = models.APIKey.objects.get(key=api_key)
                if key_obj.is_active:
                    logger.info("API key is valid and active ")
                    return True
                else:
                    logger.warning(f"API key is inactive {api_key}")
            except models.APIKey.DoesNotExist:
                logger.warning(f"API key does not exist {api_key}")

        logger.warning("Permission denied")
        return False
