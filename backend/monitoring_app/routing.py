from django.urls import re_path
from monitoring_app import consumers, ws_user

websocket_urlpatterns = [
    re_path(r"ws/photos/$", consumers.PhotoConsumer.as_asgi()),
    re_path(r"ws/user-detail/$", ws_user.UserDetail.as_asgi()),
]
