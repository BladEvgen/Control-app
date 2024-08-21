from django.conf import settings
from monitoring_app import models
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

class IsAuthenticatedOrAPIKey(BasePermission):

    def has_permission(self, request, view):
        logger = settings.LOGGING['loggers']['django'] 
        
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            user, token = jwt_authenticator.authenticate(request)
            if user and token:
                if token and token.payload.get('token_type') == 'access':
                    return True
        except (InvalidToken, AuthenticationFailed) as e:
            logger.warning(f"JWT Authentication failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during JWT authentication: {str(e)}")
            return False

        api_key = request.headers.get("X-API-KEY")
        if api_key and models.APIKey.objects.filter(key=api_key, is_active=True).exists():
            return True

        return False
