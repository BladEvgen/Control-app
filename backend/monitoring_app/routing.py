from typing import Any, cast

from django.urls import re_path

from monitoring_app import consumers, ws_user

photo_consumer_app = cast(Any, consumers.PhotoConsumer.as_asgi())
user_detail_consumer_app = cast(Any, ws_user.UserDetail.as_asgi())

websocket_urlpatterns = [
    re_path(r"ws/photos/$", photo_consumer_app),
    re_path(r"ws/user-detail/$", user_detail_consumer_app),
]
