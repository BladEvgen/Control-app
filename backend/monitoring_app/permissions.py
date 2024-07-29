from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import BasePermission
from monitoring_app import models


class IsAuthenticatedOrAPIKey(BasePermission):
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True

        jwt_authenticator = JWTAuthentication()
        try:
            user, token = jwt_authenticator.authenticate(request)
            if user and token:
                return True
        except Exception:
            pass

        api_key = request.headers.get("X-API-KEY")
        if (
            api_key
            and models.APIKey.objects.filter(key=api_key, is_active=True).exists()
        ):
            return True

        return False
