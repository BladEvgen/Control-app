from monitoring_app import models
from datetime import datetime, timezone
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


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
        data = super().validate(attrs)
        token = self.get_token(self.user)
        access_exp = datetime.fromtimestamp(token.access_token["exp"], tz=timezone.utc)
        refresh_exp = datetime.fromtimestamp(token["exp"], tz=timezone.utc)
        data["access_token_expires"] = access_exp.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        data["refresh_token_expires"] = refresh_exp.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        try:
            user_profile = models.UserProfile.objects.get(user=self.user)
            user_data = {
                "username": self.user.username,
                "is_banned": user_profile.is_banned,
                "is_staff": self.user.is_staff,
                "is_super": self.user.is_superuser,
            }
        except models.UserProfile.DoesNotExist:
            user_data = {"username": self.user.username, "is_banned": False}
        data["user"] = user_data
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom view for obtaining JWT tokens using CustomTokenObtainPairSerializer.
    """

    serializer_class = CustomTokenObtainPairSerializer
