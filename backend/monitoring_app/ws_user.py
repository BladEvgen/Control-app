import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from monitoring_app import models, serializers

logger = logging.getLogger("django")


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

    def connect(self):
        try:
            user = self.scope.get("user")
            if not user or not user.is_authenticated:
                logger.warning("Попытка подключения неавторизованного пользователя")
                self.close()
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
            self.close()

    def disconnect(self, close_code):
        try:
            user = self.scope.get("user")
            if user and user.is_authenticated:
                async_to_sync(self.channel_layer.group_discard)(
                    self.group_name, self.channel_name
                )
                logger.info(
                    f"Пользователь {user.username} отключился от сокета с каналом {self.channel_name}"
                )
        except Exception as e:
            logger.error(f"Ошибка при отключении: {str(e)}")

    def receive_json(self, content, **kwargs):
        """
        Обработка входящих JSON-сообщений.
        Помимо обычных действий, теперь обрабатывается ping:
          - {"type": "ping"} – сервер отвечает {"type": "pong"}.
        """
        try:
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
                self.send_json({"message": "IP уже актуален"})
        except models.UserProfile.DoesNotExist:
            logger.error(f"Профиль пользователя не найден для {user.username}")
            self.send_json({"error": "Профиль пользователя не найден"})
        except Exception as e:
            logger.error(f"Ошибка обновления IP для {user.username}: {str(e)}")
            self.send_json({"error": f"Ошибка обновления IP: {str(e)}"})

    def send_user_profile(self):
        try:
            user = self.scope["user"]
            logger.info(f"Отправка профиля для пользователя {user.username}")
            profile = models.UserProfile.objects.get(user=user)
            serializer = serializers.UserProfileSerializer(profile)
            self.send_json(serializer.data)
            logger.info(f"Профиль пользователя {user.username} успешно отправлен")
        except models.UserProfile.DoesNotExist:
            logger.error(f"Профиль пользователя не найден для {user.username}")
            self.send_json({"error": "Профиль пользователя не найден"})
        except Exception as e:
            logger.error(f"Ошибка получения профиля для {user.username}: {str(e)}")
            self.send_json({"error": f"Ошибка получения профиля: {str(e)}"})
