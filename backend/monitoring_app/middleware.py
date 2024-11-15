import re
from django.http import HttpResponseForbidden
from django.conf import settings


class CustomCorsAndSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        self.user_agent_regex = re.compile(
            r"Mozilla/5\.0 \(.*\) AppleWebKit/\d+\.\d+ \(KHTML, like Gecko\) Chrome/\d+\.\d+\.\d+\.\d+ Safari/\d+\.\d+"
        )

    def __call__(self, request):
        response = self.get_response(request)

        origin = request.headers.get('Origin')
        if origin in self.allowed_origins:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response["Access-Control-Allow-Credentials"] = "true"

        user_agent = request.headers.get('User-Agent', '')
        if not self.is_valid_user_agent(user_agent):
            return HttpResponseForbidden("Forbidden: Invalid User-Agent")

        return response

    def is_valid_user_agent(self, user_agent):
        return bool(self.user_agent_regex.match(user_agent))
