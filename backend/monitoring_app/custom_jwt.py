from datetime import datetime, timezone
from typing import Any, Dict, cast

from monitoring_app import models
from rest_framework import exceptions
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


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


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Custom serializer for refreshing JWT tokens with precise expiration times in UTC.

    Returns:
        dict: {
            "access": <new access token>,
            "refresh": <new refresh token> (if ROTATE_REFRESH_TOKENS is True),
            "access_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
            "refresh_token_expires": ISO8601 formatted expiration datetime in UTC (millisecond precision, 'Z' suffix),
        }
    """

    def validate(self, attrs):
        data = cast(Dict[str, Any], super().validate(attrs))

        access_token_str = data.get("access")
        refresh_token_str = data.get("refresh")

        if not access_token_str:
            raise exceptions.ValidationError("Access token not found in response")

        try:
            from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

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


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom view for refreshing JWT tokens using CustomTokenRefreshSerializer.
    """

    serializer_class = CustomTokenRefreshSerializer
