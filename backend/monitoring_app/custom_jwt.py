from monitoring_app import models
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Кастомный сериализатор для получения JWT токенов (access и refresh).

    Расширяет стандартную реализацию, добавляя к токенам минимальные данные
    о пользователе: `username`, `is_banned` (заблокирован ли пользователь) и `is_staff` (является ли администратором).

    Возвращаемые данные:
    - Токены (access и refresh).
    - Пользовательская информация:
        - `username`: Имя пользователя.
        - `is_banned`: Статус блокировки пользователя.
        - `is_staff`: Является ли пользователь персоналом.
        - `is_super`: Является ли пользовтаель администратором.
    """

    def validate(self, attrs):
        """
        Переопределяет метод валидации для добавления пользовательских данных
        в ответ JWT токенов.

        Если у пользователя существует профиль, извлекает данные из профиля, в противном случае
        возвращает только базовые данные (`username`, `is_banned=False`).

        Args:
            attrs (dict): Входящие данные для валидации.

        Returns:
            dict: Данные токенов и информация о пользователе.
        """
        data = super().validate(attrs)
        user = self.user

        try:
            user_profile = models.UserProfile.objects.get(user=user)

            data["user"] = {
                "username": user.username,
                "is_banned": user_profile.is_banned,
                "is_staff": user.is_staff,
                "is_super": user.is_superuser,
            }

        except models.UserProfile.DoesNotExist:
            data["user"] = {
                "username": user.username,
                "is_banned": False,
            }

        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Кастомное представление для получения JWT токенов (access и refresh).

    Возвращает минимальный набор данных о пользователе вместе с токенами:
    - `username`: Имя пользователя.
    - `is_banned`: Статус блокировки пользователя.
    - `is_staff`: Является ли пользователь администратором.
    """

    serializer_class = CustomTokenObtainPairSerializer
