"""Data import API (departments, staff, holidays, geo, staff removal, photos).

The upload is validated, streamed to ``MEDIA_ROOT/uploads`` and handed to the
``process_uploaded_file`` Celery task; the client polls ``import_status``.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional, cast

from celery.result import AsyncResult
from django.conf import settings
from django.views.decorators.cache import never_cache
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from monitoring_app import models, tasks

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "departments": {".csv", ".xlsx"},
    "staff": {".csv", ".xlsx"},
    "public_holidays": {".csv", ".xlsx"},
    "load_geo": {".csv", ".xlsx"},
    "delete_staff": {".csv", ".xlsx"},
    "photo": {".zip"},
}


def upload_max_bytes() -> int:
    """Upload size limit, configurable through ``UPLOAD_MAX_BYTES``."""
    return int(getattr(settings, "UPLOAD_MAX_BYTES", 2 * 1024 * 1024 * 1024))


def validate_upload(uploaded: Any, category: str) -> Optional[str]:
    """Reject before touching the disk: nothing to store if the request is invalid."""
    if not uploaded or not category:
        return "Выберите шаблон и файл."
    if not models.FileCategory.objects.filter(slug=category).exists():
        return f"Неизвестный шаблон: {category}."
    extension = os.path.splitext(uploaded.name or "")[1].lower()
    allowed = ALLOWED_EXTENSIONS.get(category, set())
    if extension not in allowed:
        return (
            f"Для шаблона «{category}» допустимы файлы {', '.join(sorted(allowed))}, "
            f"а получен «{extension or 'без расширения'}»."
        )
    limit = upload_max_bytes()
    if uploaded.size and uploaded.size > limit:
        return (
            f"Файл больше допустимых {limit // (1024 * 1024)} МБ "
            f"({uploaded.size // (1024 * 1024)} МБ)."
        )
    return None


def store_upload(uploaded: Any) -> str:
    """Stream the upload to disk chunk by chunk; the file never sits in memory whole."""
    target_dir = Path(settings.MEDIA_ROOT) / "uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{os.path.splitext(uploaded.name or '')[1].lower()}"
    with open(target, "wb") as handle:
        for chunk in uploaded.chunks():
            handle.write(chunk)
    return str(target)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


_ERROR = openapi.Schema(
    type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)}
)


@swagger_auto_schema(
    method="get",
    operation_summary="Шаблоны импорта",
    operation_description="Список шаблонов, родительские отделы для delete_staff, "
    "лимит размера и допустимые расширения по шаблонам.",
    tags=["Import"],
    responses={
        200: openapi.Response(
            "Параметры формы импорта",
            examples={
                "application/json": {
                    "categories": [{"slug": "staff", "name": "Сотрудники"}],
                    "parentDepartments": [{"id": 2, "name": "Медицинский факультет"}],
                    "maxUploadMb": 2048,
                    "allowedExtensions": {"staff": [".csv", ".xlsx"], "photo": [".zip"]},
                }
            },
        )
    },
)
@swagger_auto_schema(
    method="post",
    operation_summary="Загрузить файл импорта",
    operation_description="Файл сохраняется и уходит в Celery. Ответ 202 с taskId; "
    "прогресс: GET /api/import/status/{taskId}/.",
    tags=["Import"],
    manual_parameters=[
        openapi.Parameter(
            "category",
            openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            required=True,
            enum=sorted(ALLOWED_EXTENSIONS),
            description="Слаг шаблона.",
        ),
        openapi.Parameter(
            "file",
            openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description=".csv/.xlsx, для photo — .zip.",
        ),
        openapi.Parameter(
            "parentDepartment",
            openapi.IN_FORM,
            type=openapi.TYPE_INTEGER,
            required=False,
            description="Только для delete_staff.",
        ),
        openapi.Parameter(
            "archiveMissing",
            openapi.IN_FORM,
            type=openapi.TYPE_BOOLEAN,
            required=False,
            description="staff: архивировать отсутствующих в файле.",
        ),
        openapi.Parameter(
            "forceArchive",
            openapi.IN_FORM,
            type=openapi.TYPE_BOOLEAN,
            required=False,
            description="staff: даже если затронута больше половины.",
        ),
    ],
    responses={
        202: openapi.Response(
            "Поставлено в очередь", examples={"application/json": {"taskId": "8f1c…"}}
        ),
        400: openapi.Response("Неверный шаблон, расширение или размер", _ERROR),
        500: openapi.Response("Не удалось сохранить файл", _ERROR),
        503: openapi.Response("Celery/Redis недоступны", _ERROR),
    },
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def data_import(request: Request) -> Response:
    """GET: templates, parent departments and size limit. POST: queue an upload."""
    if request.method == "GET":
        return Response(
            {
                "categories": list(
                    models.FileCategory.objects.order_by("name").values("slug", "name")
                ),
                "parentDepartments": list(
                    models.ParentDepartment.objects.exclude(id=1)
                    .order_by("name")
                    .values("id", "name")
                ),
                "maxUploadMb": upload_max_bytes() // (1024 * 1024),
                "allowedExtensions": {k: sorted(v) for k, v in ALLOWED_EXTENSIONS.items()},
            }
        )

    uploaded = request.FILES.get("file")
    category = str(request.data.get("category") or "").strip()
    error = validate_upload(uploaded, category)
    if error:
        logger.warning("data_import: отклонено — %s", error)
        return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

    try:
        stored_path = store_upload(uploaded)
    except OSError as exc:
        logger.error("data_import: не удалось сохранить файл — %s", exc)
        return Response(
            {"error": f"Не удалось сохранить файл: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    options = {
        "parent_department": str(request.data.get("parentDepartment") or ""),
        "archive_missing": _truthy(request.data.get("archiveMissing")),
        "force": _truthy(request.data.get("forceArchive")),
    }
    try:
        task = cast(Any, tasks.process_uploaded_file).delay(stored_path, category, options)
    except Exception as exc:  # noqa: BLE001 — broker down: tell the user, drop the file
        logger.error("data_import: не удалось поставить задачу — %s", exc)
        try:
            os.remove(stored_path)
        except OSError:
            pass
        return Response(
            {
                "error": "Не удалось поставить файл в очередь обработки. "
                "Проверьте, что Celery и Redis запущены."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.info(
        "data_import: категория=%s файл=%s задача=%s",
        category,
        getattr(uploaded, "name", ""),
        task.id,
    )
    return Response({"taskId": task.id}, status=status.HTTP_202_ACCEPTED)


@swagger_auto_schema(
    method="get",
    operation_summary="Статус импорта",
    tags=["Import"],
    responses={
        200: openapi.Response(
            "Состояние задачи Celery",
            examples={
                "application/json": {
                    "taskId": "8f1c…",
                    "state": "PROGRESS",
                    "stage": "Сотрудники",
                    "processed": 412,
                    "total": 980,
                    "message": "Сотрудники: 412 из 980",
                    "summary": [],
                    "ready": False,
                }
            },
        )
    },
)
@never_cache
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def import_status(request: Request, task_id: str) -> Response:
    """State and progress published by ``process_uploaded_file``."""
    _ = request
    result = AsyncResult(task_id)
    payload: dict[str, Any] = {
        "taskId": task_id,
        "state": result.state,
        "stage": None,
        "processed": 0,
        "total": 0,
        "message": "",
        "summary": [],
        "ready": result.ready(),
    }
    if result.state == "PROGRESS" and isinstance(result.info, dict):
        stage = result.info.get("stage")
        processed = result.info.get("processed", 0)
        total = result.info.get("total", 0)
        payload.update(stage=stage, processed=processed, total=total)
        payload["message"] = (
            f"{stage}: {processed} из {total}" if total else f"{stage}: {processed}"
        )
    elif result.state == "SUCCESS":
        data = result.result if isinstance(result.result, dict) else {}
        payload["summary"] = data.get("summary", [])
        payload["message"] = "Обработка завершена."
    elif result.state == "FAILURE":
        payload["message"] = str(result.info)
    elif result.state == "PENDING":
        payload["message"] = "Задача в очереди."
    return Response(payload)
