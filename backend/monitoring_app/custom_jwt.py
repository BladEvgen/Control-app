from datetime import datetime, timezone
from typing import Any, Dict, cast

from rest_framework import exceptions
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from monitoring_app import models


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer for obtaining JWT tokens with precise expiration times in UTC.

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

    def validate(self, attrs):
        data = cast(Dict[str, Any], super().validate(attrs))
        user = self.user
        if user is None:
            raise exceptions.AuthenticationFailed("User is not authenticated")

        token = self.get_token(user)
        access_exp_seconds = float(token.access_token["exp"])
        refresh_exp_seconds = float(token["exp"])
        access_exp = datetime.fromtimestamp(access_exp_seconds, tz=timezone.utc)
        refresh_exp = datetime.fromtimestamp(refresh_exp_seconds, tz=timezone.utc)
        data["access_token_expires"] = access_exp.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        data["refresh_token_expires"] = refresh_exp.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
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


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom view for obtaining JWT tokens using CustomTokenObtainPairSerializer.
    """

    serializer_class = CustomTokenObtainPairSerializer
