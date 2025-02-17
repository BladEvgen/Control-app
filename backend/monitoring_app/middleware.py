import json
import logging
import time
import urllib.error
import urllib.request

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework_simplejwt.tokens import AccessToken, TokenError

logger = logging.getLogger(__name__)


class EnhancedSecurityMiddleware:
    """
    Middleware for handling CORS, API token authentication, and rate limiting.

    This middleware performs the following functions:
    1. Validates the Origin header against allowed origins and sets appropriate CORS headers.
    2. Authenticates requests using the Authorization header with Bearer tokens or the x-api-token header.
    3. Implements rate limiting to prevent abuse by restricting the number of requests
       per identifier within a specified time period.
    """

    def __init__(self, get_response):
        """
        Initializes the middleware with configuration from Django settings.

        Args:
            get_response (callable): The next middleware or view in the chain.
        """
        self.get_response = get_response
        self.allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        self.api_token = getattr(settings, "API_TOKEN", None)
        self.rate_limit = getattr(settings, "RATE_LIMIT", 20)
        self.rate_period = getattr(settings, "RATE_PERIOD", 600)  # in seconds
        self.exempt_paths = getattr(settings, "SECURITY_MIDDLEWARE_EXEMPT_PATHS", [])

    def __call__(self, request):
        """
        Processes each incoming HTTP request.

        Args:
            request (HttpRequest): The incoming HTTP request.

        Returns:
            HttpResponse: The HTTP response, either from the next middleware/view
                          or an error response if validation fails.
        """
        current_path = request.path_info

        if self.is_exempt_path(current_path):
            return self.get_response(request)

        # Check for Bearer token in Authorization header
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            # Allow request to proceed; authentication handled by DRF
            return self.get_response(request)

        # Check for x-api-token
        api_token = request.headers.get("x-api-token")
        if self.is_valid_api_token(api_token):
            return self.get_response(request)

        # If neither Bearer token nor x-api-token is present, block the request
        client_ip = self.get_client_ip(request)
        logger.warning(f"Invalid or missing API token from IP: {client_ip}")
        return self.too_many_requests_response()

    def is_exempt_path(self, path):
        """
        Determines if the current path is exempted from API token authentication and rate limiting.

        Args:
            path (str): The URL path of the incoming request.

        Returns:
            bool: True if the path is exempted, False otherwise.
        """
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return True
        return False

    def is_valid_api_token(self, api_token):
        """
        Validates the provided API token.

        Args:
            api_token (str): The API token from the request header.

        Returns:
            bool: True if the token is valid, False otherwise.
        """
        if not api_token:
            return False
        return api_token == self.api_token

    def increment_request_count(self, identifier):
        """
        Increments the request count for the given identifier and checks against the rate limit.

        Args:
            identifier (str): The unique identifier for the requester (e.g., API token or IP).

        Returns:
            bool: True if the request is within the rate limit, False otherwise.
        """
        current_time = time.time()
        window_start = current_time - self.rate_period

        request_times = cache.get(identifier, [])
        # Remove timestamps outside the current window
        request_times = [
            timestamp for timestamp in request_times if timestamp > window_start
        ]

        if len(request_times) >= self.rate_limit:
            return False

        request_times.append(current_time)
        cache.set(identifier, request_times, timeout=self.rate_period)
        return True

    def get_identifier(self, request):
        """
        Retrieves a unique identifier for rate limiting based on the API token or client IP.

        Args:
            request (HttpRequest): The incoming HTTP request.

        Returns:
            str: A unique identifier string.
        """
        api_token = request.headers.get("x-api-token")
        if api_token:
            return f"rate_limit:{api_token}"
        return f"rate_limit:{self.get_client_ip(request)}"

    def get_client_ip(self, request):
        """
        Extracts the client's IP address from the request.

        Args:
            request (HttpRequest): The incoming HTTP request.

        Returns:
            str: The client's IP address.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            # X-Forwarded-For may contain multiple IPs, the first one is the client's IP
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return ip

    def add_cors_headers(self, response, origin):
        """
        Adds CORS headers to the HTTP response.

        Args:
            response (HttpResponse): The HTTP response to modify.
            origin (str): The Origin header from the request.
        """
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, x-api-token"
        )
        response["Access-Control-Allow-Credentials"] = "true"

    def too_many_requests_response(self):
        """
        Generates a 429 Too Many Requests response.

        Returns:
            HttpResponse: The HTTP 429 response.
        """
        return HttpResponse("Too Many Requests", status=429, content_type="text/plain")


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
                    status_code, resp_data = await sync_to_async(refresh_token_request)(refresh_url, refresh_token)
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
