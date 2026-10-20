import json
import logging
import urllib.error
import urllib.request

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)


def get_refresh_url():
    """
    Формирует URL для обновления токена на основе MAIN_IP из настроек.
    """
    main_ip = getattr(settings, "MAIN_IP", "http://localhost:8000")
    return f"{main_ip}/api/token/refresh/"


@database_sync_to_async
def get_user_from_token(token):
    try:
        access_token = AccessToken(token)
    except TokenError:
        return AnonymousUser()
    user_id = access_token.get("user_id")
    if not user_id:
        return AnonymousUser()
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        return user
    except User.DoesNotExist:
        return AnonymousUser()


def refresh_token_request(refresh_url, refresh_token):
    """
    Выполняет синхронный POST-запрос с использованием urllib.request для обновления токенов.
    Возвращает кортеж (status_code, response_data).
    """
    data = json.dumps({"refresh": refresh_token}).encode("utf-8")
    req = urllib.request.Request(
        refresh_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            resp_data = response.read()
            return status_code, resp_data
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return None, None


class JWTAuthMiddleware:
    """
    Middleware, который извлекает access-токен из query-параметров.
    Если токен недействителен, пытается обновить его по refresh-токену из cookies.
    middleware пропускается и пользователь устанавливается как AnonymousUser.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if path.startswith("/ws/photos/"):
            scope["user"] = AnonymousUser()
            return await self.inner(scope, receive, send)

        query_string = scope.get("query_string", b"").decode("utf-8")
        token = None
        if query_string:
            params = dict(pair.split("=") for pair in query_string.split("&") if "=" in pair)
            token = params.get("token")
        if token:
            try:
                _ = AccessToken(token)
            except Exception:
                headers = dict(scope.get("headers", []))
                cookie_bytes = headers.get(b"cookie", b"")
                cookie_str = cookie_bytes.decode("utf-8") if cookie_bytes else ""
                cookies = {}
                for pair in cookie_str.split(";"):
                    if "=" in pair:
                        k, v = pair.strip().split("=", 1)
                        cookies[k] = v
                refresh_token = cookies.get("refresh_token")
                if refresh_token:
                    refresh_url = get_refresh_url()
                    status_code, resp_data = await sync_to_async(refresh_token_request)(
                        refresh_url, refresh_token
                    )
                    if status_code == 200 and resp_data:
                        try:
                            new_tokens = json.loads(resp_data)
                            new_access_token = new_tokens.get("access")
                            token = new_access_token
                        except Exception:
                            scope["user"] = AnonymousUser()
                            return await self.inner(scope, receive, send)
                    else:
                        scope["user"] = AnonymousUser()
                        return await self.inner(scope, receive, send)
                else:
                    scope["user"] = AnonymousUser()
                    return await self.inner(scope, receive, send)
            user = await get_user_from_token(token)
            scope["user"] = user
        else:
            scope["user"] = AnonymousUser()
        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)


class StaffActivityMiddleware:
    """Цифровая явка по действиям пользователя, привязанного к Staff.user.

    Считаются только действия человека: изменяющие запросы и страницы админки.
    (POST /api/activity/heartbeat/), который фронт шлёт только при реальном вводе.

    request.user читается после ответа: DRF аутентифицирует JWT внутри view и
    проставляет пользователя в исходный HttpRequest.

    Args:
        get_response (Callable[[HttpRequest], HttpResponse]): Функция получения
            следующего middleware или view в цепочке Django.

    Returns:
        HttpResponse: HTTP-ответ, возвращенный нижележащими слоями.

    Raises:
        Exception: Исключения, возникающие при выполнении `get_response`, пробрасываются
            дальше. Ошибки сервиса `touch_activity` перехватываются и логируются внутри метода.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or response.status_code >= 400:
            return response
        if not hasattr(user, "pk"):
            return response
        user_action = request.method not in ("GET", "HEAD", "OPTIONS")
        if not (user_action or request.path.startswith("/admin/")):
            return response
        from monitoring_app.services.attendance_day import touch_activity

        try:
            touch_activity(user, "admin" if request.path.startswith("/admin/") else "web")
        except Exception:
            logger.exception("touch_activity failed user_id=%s", user.pk)
        return response
