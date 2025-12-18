from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, get_user, login
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from monitoring_app.permissions import IsAuthenticatedOrAPIKey


def _load_login_html():
    """Загружает HTML шаблон формы логина для Swagger.

    Returns:
        str: HTML содержимое шаблона формы логина.
    """
    template_path = Path(__file__).parent.parent / "templates" / "swagger_login.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, IOError):
        return render_to_string("swagger_login.html", {})


LOGIN_HTML = _load_login_html()


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def swagger_session_login(request):
    """Эндпоинт для сессионной аутентификации в Swagger UI.

    CSRF exempt, так как вызывается из JavaScript формы логина.

    Args:
        request: HTTP запрос с полями username и password.

    Returns:
        Response: JSON ответ с результатом аутентификации.
            - 200: Успешная аутентификация с полем success=True.
            - 400: Отсутствуют username или password.
            - 401: Неверные учетные данные.
    """
    username = request.data.get("username") or request.POST.get("username")
    password = request.data.get("password") or request.POST.get("password")

    if not username or not password:
        return Response(
            {"detail": "Username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return Response({"success": True, "username": user.username})
    else:
        return Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def swagger_session_logout(request):
    """Эндпоинт для выхода из сессии в Swagger UI.

    CSRF exempt, так как вызывается из JavaScript и использует сессионную аутентификацию.

    Args:
        request: HTTP запрос.

    Returns:
        Response: JSON ответ с полем success=True и удалением cookies сессии.
    """
    from django.contrib.auth import logout

    logout(request)
    response = Response({"success": True, "message": "Logged out successfully"})
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    csrf_cookie_name = getattr(settings, "CSRF_COOKIE_NAME", "csrftoken")
    response.delete_cookie(csrf_cookie_name)
    if csrf_cookie_name != "csrftoken":
        response.delete_cookie("csrftoken")
    return response


def swagger_ui_with_login(request, schema_view, ui="swagger"):
    """Кастомный view для Swagger UI с формой логина.

    Показывает форму логина для неаутентифицированных пользователей
    и Swagger UI для аутентифицированных. Использует сессионную аутентификацию.

    Args:
        request: HTTP запрос.
        schema_view: Экземпляр SchemaView для генерации схемы.
        ui (str): Тип UI интерфейса ('swagger' или 'redoc'). По умолчанию 'swagger'.

    Returns:
        HttpResponse: HTML ответ с формой логина или Swagger/ReDoc UI.
    """

    if not isinstance(request, Request):
        user = get_user(request)
        if user and user.is_authenticated:
            request.user = user

    permission = IsAuthenticatedOrAPIKey()
    has_permission = permission.has_permission(request, None)

    if not has_permission:
        return HttpResponse(
            LOGIN_HTML.encode("utf-8"), content_type="text/html; charset=utf-8"
        )

    response = schema_view.with_ui(ui)(request)

    try:
        if not getattr(response, "_is_rendered", True):
            response.render()
    except AttributeError:
        pass

    if hasattr(response, "content") and isinstance(response.content, bytes):
        content_str = response.content.decode("utf-8", errors="ignore")
        if "<!DOCTYPE html" in content_str[:1000] or "<html" in content_str[:1000]:
            script_content = """
<script>
(function() {
    let isLoggingOut = false;
    const processedElements = new WeakSet();
    
    fetch('/api/swagger-login/', {
        method: 'GET',
        credentials: 'include'
    }).then(response => {
        if (response.ok) {
            console.log('Session authentication active');
        }
    }).catch(err => {
        console.error('Session check failed:', err);
    });
    
    function handleLogout(e) {
        if (isLoggingOut) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
        
        e.preventDefault();
        e.stopPropagation();
        
        isLoggingOut = true;
        
        fetch('/api/swagger-logout/', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            }
        }).then(response => {
            window.location.href = window.location.pathname;
        }).catch(() => {
            window.location.href = window.location.pathname;
        });
        
        return false;
    }
    

    function overrideLogout() {
        const logoutLinks = document.querySelectorAll('a[href*="logout"], a[href*="/accounts/logout/"]');
        logoutLinks.forEach(link => {
            if (!processedElements.has(link)) {
                processedElements.add(link);
                link.addEventListener('click', handleLogout, { once: true });
            }
        });
        
        const logoutButtons = document.querySelectorAll('.logout, [class*="logout"]');
        logoutButtons.forEach(btn => {
            if (!processedElements.has(btn)) {
                processedElements.add(btn);
                btn.addEventListener('click', handleLogout, { once: true });
            }
        });
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', overrideLogout);
    } else {
        overrideLogout();
    }
    

    const observer = new MutationObserver(function(mutations) {
        overrideLogout();
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
})();
</script>
"""
            script_bytes = script_content.encode("utf-8")
            if b"</body>" in response.content:
                response.content = response.content.replace(
                    b"</body>", script_bytes + b"</body>"
                )
            else:
                response.content = response.content + script_bytes

    return response


def swagger_json_with_login(request, schema_view, format_param=None):
    """Кастомный view для получения JSON/YAML схемы с проверкой авторизации.

    Поддерживает сессионную, JWT и API Key аутентификацию.
    Возвращает пустую схему для неавторизованных пользователей,
    чтобы скрыть эндпоинты.

    Args:
        request: HTTP запрос.
        schema_view: Экземпляр SchemaView для генерации схемы.
        format_param (str, optional): Формат схемы ('.json' или '.yaml').

    Returns:
        HttpResponse или JsonResponse: JSON/YAML схема или пустая схема
            для неавторизованных пользователей.
    """

    if not isinstance(request, Request):
        user = get_user(request)
        if user and user.is_authenticated:
            request.user = user

    permission = IsAuthenticatedOrAPIKey()
    has_permission = permission.has_permission(request, None)

    if not has_permission:
        empty_schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "API",
                "version": "v1",
                "description": "Войдите в систему для доступа к API документации",
            },
            "paths": {},
            "components": {},
        }
        if format_param == ".yaml":
            try:
                import yaml

                return HttpResponse(
                    yaml.dump(
                        empty_schema, default_flow_style=False, allow_unicode=True
                    ).encode("utf-8"),
                    content_type="application/x-yaml",
                )
            except ImportError:
                pass
        return JsonResponse(empty_schema)

    without_ui_view = schema_view.without_ui()
    if format_param:
        return without_ui_view(request, **{"format": format_param})
    return without_ui_view(request)
