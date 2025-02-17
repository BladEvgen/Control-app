import os
import monitoring_app.routing
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from monitoring_app.middleware import JWTAuthMiddlewareStack  

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            monitoring_app.routing.websocket_urlpatterns
        )
    ),
})