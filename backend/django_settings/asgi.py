import os
import logging

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.middleware import BaseMiddleware
from channels.exceptions import DenyConnection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

logger = logging.getLogger("django")

django_asgi_app = get_asgi_application()


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        logger.info(f"Request scope: {scope}")
        try:
            return await super().__call__(scope, receive, send)
        except Exception as e:
            logger.error("Error processing WebSocket request: %s", e)
            raise DenyConnection()


import monitoring_app.routing

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": LoggingMiddleware(
            AuthMiddlewareStack(URLRouter(monitoring_app.routing.websocket_urlpatterns))
        ),
    }
)
