from __future__ import annotations

import logging
import time

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("monitoring_app.face_lab")

FACE_LAB_PATH = "/api/face-lab/"


class FaceLabRequestLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if FACE_LAB_PATH not in request.path:
            return None
        request._face_lab_req_start = time.perf_counter()
        return None

    def process_response(self, request, response):
        start = getattr(request, "_face_lab_req_start", None)
        if start is None:
            return response

        elapsed_ms = (time.perf_counter() - start) * 1000
        uid = None
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            uid = getattr(user, "id", None)

        get_keys = sorted(request.GET.keys()) if request.GET else []

        logger.info(
            "face_lab %s %s -> %s in %.1fms user_id=%s get_keys=%s",
            request.method,
            request.path,
            getattr(response, "status_code", "?"),
            elapsed_ms,
            uid,
            get_keys,
        )
        return response
