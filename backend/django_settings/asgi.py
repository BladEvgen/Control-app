import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from monitoring_app.middleware import JWTAuthMiddlewareStack
import monitoring_app.routing

# Use the initialized application
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            monitoring_app.routing.websocket_urlpatterns
        )
    ),
})