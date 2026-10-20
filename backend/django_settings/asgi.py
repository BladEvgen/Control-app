import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_settings.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()


def _warm_models() -> None:
    """Load face engine + PAD CLIP in the background: the web UI answers right after a
    restart; a face request arriving earlier waits on the same load lock."""
    import logging

    try:
        from monitoring_app import ml, photo_pad

        ml.load_face_engine()
        photo_pad._clip(photo_pad.normalize_device())
        photo_pad.load_head()
    except Exception:
        logging.getLogger("monitoring_app.ml").exception("Model warmup on startup failed")


if os.getenv("WARM_MODELS_ON_START", "1") == "1":
    import threading

    threading.Thread(target=_warm_models, name="warm-models", daemon=True).start()

from channels.routing import ProtocolTypeRouter, URLRouter

import monitoring_app.routing
from monitoring_app.middleware import JWTAuthMiddlewareStack

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(monitoring_app.routing.websocket_urlpatterns)
        ),
    }
)
