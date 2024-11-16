import os
import logging
from datetime import datetime

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.middleware import BaseMiddleware
from channels.exceptions import DenyConnection
from django.core.asgi import get_asgi_application

import monitoring_app.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

logger = logging.getLogger("django")

django_asgi_app = get_asgi_application()


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging HTTP and WebSocket requests and responses.

    This middleware intercepts incoming HTTP and WebSocket connections to log
    relevant information such as request method, path, client details, and
    timestamps. It also logs responses and handles exceptions by logging them
    appropriately.
    """

    async def __call__(self, scope, receive, send):
        """
        Entry point for the middleware.

        Determines the type of connection (HTTP or WebSocket) and delegates
        to the appropriate logging method.

        Args:
            scope (dict): The connection scope.
            receive (callable): A callable to receive messages.
            send (callable): A callable to send messages.

        Returns:
            Awaitable: The response from the underlying application.
        """
        if scope["type"] == "http":
            return await self.log_http(scope, receive, send)
        elif scope["type"] == "websocket":
            return await self.log_websocket(scope, receive, send)
        else:
            return await super().__call__(scope, receive, send)

    async def log_http(self, scope, receive, send):
        """
        Logs HTTP requests and responses.

        Args:
            scope (dict): The HTTP connection scope.
            receive (callable): A callable to receive messages.
            send (callable): A callable to send messages.

        Returns:
            Awaitable: The response from the underlying application.
        """
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "UNKNOWN")
        client = scope.get("client", ("unknown", "unknown"))
        request_time = datetime.now()

        logger.info(f"HTTP Request: {method} {path} from {client[0]}:{client[1]} at {request_time}")

        async def send_wrapper(message):
            """
            Wraps the send callable to log HTTP responses.

            Args:
                message (dict): The message to send.
            """
            if message["type"] == "http.response.start":
                status = message.get("status", "UNKNOWN")
                logger.info(
                    f"HTTP Response: {method} {path} to {client[0]}:{client[1]} with status {status}"
                )
            await send(message)

        try:
            await super().__call__(scope, receive, send_wrapper)
        except Exception as e:
            logger.exception(f"Exception in HTTP request: {method} {path} - {e}")
            raise

    async def log_websocket(self, scope, receive, send):
        """
        Logs WebSocket connections and disconnections.

        Args:
            scope (dict): The WebSocket connection scope.
            receive (callable): A callable to receive messages.
            send (callable): A callable to send messages.

        Returns:
            Awaitable: The response from the underlying application.
        """
        path = scope.get("path", "UNKNOWN")
        client = scope.get("client", ("unknown", "unknown"))
        connection_time = datetime.now()

        logger.info(
            f"WebSocket Connection: {path} from {client[0]}:{client[1]} at {connection_time}"
        )

        async def send_wrapper(message):
            """
            Wraps the send callable to log WebSocket disconnections.

            Args:
                message (dict): The message to send.
            """
            if message["type"] == "websocket.close":
                disconnection_time = datetime.now()
                logger.info(
                    f"WebSocket Disconnection: {path} to {client[0]}:{client[1]} at {disconnection_time}"
                )
            await send(message)

        try:
            await super().__call__(scope, receive, send_wrapper)
        except Exception as e:
            logger.exception(f"Exception in WebSocket connection: {path} - {e}")
            raise DenyConnection()


application = ProtocolTypeRouter(
    {
        "http": LoggingMiddleware(django_asgi_app),
        "websocket": LoggingMiddleware(
            AuthMiddlewareStack(URLRouter(monitoring_app.routing.websocket_urlpatterns))
        ),
    }
)
