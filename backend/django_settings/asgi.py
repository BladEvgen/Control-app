import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')
django.setup()  

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import monitoring_app.routing  

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(
        monitoring_app.routing.websocket_urlpatterns
    ),
})
