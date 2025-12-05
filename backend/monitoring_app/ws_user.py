import logging
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from monitoring_app import models, serializers

logger = logging.getLogger(__name__)

WS_CLOSE_TOKEN_EXPIRED = 4001
WS_CLOSE_TOKEN_INVALID = 4002
WS_CLOSE_REFRESH_EXPIRED = 4003
WS_CLOSE_AUTH_FAILED = 4004


class UserDetail(JsonWebsocketConsumer):
    """
    WebSocket-консьюмер для работы с профилем пользователя.
    При подключении:
      - Проверяется аутентификация. Если пользователь не аутентифицирован – закрываем соединение.
      - Если аутентифицирован – отправляется актуальный профиль и пользователь добавляется в индивидуальную группу.
    Клиент может отправлять следующие команды:
      - {"action": "get_profile"} – для запроса профиля.
      - {"action": "update_ip", "ip": "<ip-адрес>"} – для обновления IP.
      - {"type": "ping"} – для проверки соединения (сервер ответит {"type": "pong"}).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None

    def connect(self):
        try:
            user = self.scope.get("user")
            if not user or not user.is_authenticated:
                logger.warning("Попытка подключения неавторизованного пользователя")
                self.close(code=WS_CLOSE_AUTH_FAILED)
                return

            query_string = self.scope.get("query_string", b"").decode("utf-8")
            token = None
            if query_string:
                params = dict(pair.split("=") for pair in query_string.split("&") if "=" in pair)
                token = params.get("token")

            if token:
                try:
                    access_token = AccessToken(token)
                    exp = access_token.get("exp", 0)
                    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(
                        timezone.utc
                    ):
                        logger.warning(f"Токен пользователя {user.username} истек при подключении")
                        self.close(code=WS_CLOSE_TOKEN_EXPIRED)
                        return
                except TokenError as e:
                    logger.warning(f"Невалидный токен при подключении: {str(e)}")
                    self.close(code=WS_CLOSE_TOKEN_INVALID)
                    return
                except Exception as e:
                    logger.error(f"Ошибка проверки токена: {str(e)}")
                    self.close(code=WS_CLOSE_TOKEN_INVALID)
                    return

            self.accept()
            self.group_name = f"user_{user.id}"
            async_to_sync(self.channel_layer.group_add)(
                self.group_name, self.channel_name
            )
            logger.info(
                f"Пользователь {user.username} подключился к сокету с каналом {self.channel_name}"
            )
            self.send_user_profile()
        except Exception as e:
            logger.error(f"Ошибка при подключении пользователя: {str(e)}")
            self.close(code=WS_CLOSE_AUTH_FAILED)

    def disconnect(self, close_code):  # noqa: ARG002
        """
        Обработка отключения WebSocket соединения.

        Args:
            close_code: Код закрытия соединения (не используется, но требуется для переопределения метода)
        """
        try:
            user = self.scope.get("user")
            if user and user.is_authenticated and hasattr(self, "group_name") and self.group_name:
                async_to_sync(self.channel_layer.group_discard)(
                    self.group_name, self.channel_name
                )
                logger.info(
                    f"Пользователь {user.username} отключился от сокета с каналом {self.channel_name}"
                )
        except Exception as e:
            logger.error(f"Ошибка при отключении: {str(e)}")

    def _check_token_validity(self):
        """
        Проверяет валидность токена пользователя.
        Возвращает True если токен валиден, False если нужно обновить.
        """
        try:
            user = self.scope.get("user")
            if not user or not user.is_authenticated:
                return False

            query_string = self.scope.get("query_string", b"").decode("utf-8")
            token = None
            if query_string:
                params = dict(pair.split("=") for pair in query_string.split("&") if "=" in pair)
                token = params.get("token")

            if not token:
                return False

            try:
                access_token = AccessToken(token)
                exp = access_token.get("exp", 0)
                if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(
                    timezone.utc
                ):
                    logger.warning(f"Токен пользователя {user.username} истек")
                    return False
                return True
            except TokenError:
                logger.warning(f"Невалидный токен для пользователя {user.username}")
                return False
        except Exception as e:
            logger.error(f"Ошибка проверки токена: {str(e)}")
            return False

    def receive_json(self, content, **kwargs):
        """
        Обработка входящих JSON-сообщений.
        Помимо обычных действий, теперь обрабатывается ping:
          - {"type": "ping"} – сервер отвечает {"type": "pong"}.
        """
        try:
            if not self._check_token_validity():
                logger.warning("Токен невалиден, отправка сообщения о необходимости обновления")
                self.send_json(
                    {
                        "error": "token_expired",
                        "message": "Токен истек или невалиден. Необходимо обновить токен.",
                        "action": "refresh_token",
                    }
                )
                self.close(code=WS_CLOSE_TOKEN_EXPIRED)
                return

            user = self.scope.get("user")
            logger.info(
                f"Получено сообщение от пользователя {user.username if user else 'неизвестно'}: {content}"
            )

            if content.get("type") == "ping":
                logger.info("Получен ping, отправка pong")
                self.send_json({"type": "pong"})
                return

            action = content.get("action")
            if not action:
                logger.warning("Действие не указано в сообщении")
                self.send_json({"error": "Действие не указано"})
                return

            if action == "get_profile":
                self.send_user_profile()
            elif action == "update_ip":
                ip = content.get("ip")
                if ip:
                    self.update_ip(ip)
                else:
                    logger.warning("В сообщении 'update_ip' не передан IP")
                    self.send_json({"error": "IP не передан"})
            else:
                logger.warning(f"Неизвестное действие: {action}")
                self.send_json({"error": "Неизвестное действие"})
        except Exception as e:
            logger.error(f"Ошибка в receive_json: {str(e)}")
            self.send_json({"error": f"Ошибка обработки сообщения: {str(e)}"})

    def update_ip(self, ip):
        try:
            if not self._check_token_validity():
                logger.warning("Токен невалиден при обновлении IP")
                self.send_json(
                    {
                        "error": "token_expired",
                        "message": "Токен истек или невалиден. Необходимо обновить токен.",
                        "action": "refresh_token",
                    }
                )
                self.close(code=WS_CLOSE_TOKEN_EXPIRED)
                return

            user = self.scope["user"]
            logger.info(
                f"Пользователь {user.username} инициирует обновление IP на {ip}"
            )
            profile = models.UserProfile.objects.get(user=user)
            if profile.last_login_ip != ip:
                profile.last_login_ip = ip
                profile.save(update_fields=["last_login_ip"])
                logger.info(f"Пользователь {user.username} успешно обновил IP на {ip}")
                self.send_user_profile()
            else:
                logger.info(
                    f"Пользователь {user.username} отправил уже актуальный IP: {ip}"
                )
                self.send_json({"message": "IP уже актуален", "type": "info"})
        except models.UserProfile.DoesNotExist:
            logger.error(f"Профиль пользователя не найден для {user.username}")
            self.send_json({"error": "Профиль пользователя не найден", "type": "error"})
        except Exception as e:
            logger.error(f"Ошибка обновления IP для {user.username}: {str(e)}")
            self.send_json({"error": f"Ошибка обновления IP: {str(e)}", "type": "error"})

    def send_user_profile(self):
        try:
            if not self._check_token_validity():
                logger.warning("Токен невалиден при отправке профиля")
                self.send_json(
                    {
                        "error": "token_expired",
                        "message": "Токен истек или невалиден. Необходимо обновить токен.",
                        "action": "refresh_token",
                    }
                )
                self.close(code=WS_CLOSE_TOKEN_EXPIRED)
                return

            user = self.scope["user"]
            logger.info(f"Отправка профиля для пользователя {user.username}")
            profile = models.UserProfile.objects.get(user=user)
            serializer = serializers.UserProfileSerializer(profile)
            data = serializer.data
            if isinstance(data, dict):
                data["type"] = "user_profile"
                data["timestamp"] = datetime.now(timezone.utc).isoformat()
            self.send_json(data)
            logger.info(f"Профиль пользователя {user.username} успешно отправлен")
        except models.UserProfile.DoesNotExist:
            logger.error(f"Профиль пользователя не найден для {user.username}")
            self.send_json({"error": "Профиль пользователя не найден", "type": "error"})
        except Exception as e:
            logger.error(f"Ошибка получения профиля для {user.username}: {str(e)}")
            self.send_json({"error": f"Ошибка получения профиля: {str(e)}", "type": "error"})
