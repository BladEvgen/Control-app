from django.urls import re_path
from monitoring_app import consumers

websocket_urlpatterns = [
    re_path(r'ws/photos/$', consumers.PhotoConsumer.as_asgi()),
]
