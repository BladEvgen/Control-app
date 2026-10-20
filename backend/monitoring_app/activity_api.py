"""Цифровая явка: heartbeat из SPA и «сотрудник работает» по staff-JWT (вход по лицу)."""

import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from monitoring_app.authentication import StaffJWTAuthentication
from monitoring_app.permissions import IsStaffToken
from monitoring_app.services.attendance_day import record_interval, touch_activity

MAX_INGEST_HOURS = 16
FUTURE_SKEW = datetime.timedelta(minutes=5)


@swagger_auto_schema(
    method="post",
    operation_summary="Heartbeat активности пользователя",
    operation_description="SPA шлёт раз в 5 минут, только если был реальный ввод и вкладка видна.",
    tags=["Activity"],
    responses={204: "Отмечено"},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def activity_heartbeat(request):
    touch_activity(request.user, "spa")
    return Response(status=status.HTTP_204_NO_CONTENT)


@swagger_auto_schema(
    method="post",
    operation_summary="«Сотрудник работает» — от клиента/внешней системы удалёнщика",
    operation_description=(
        "Только с токеном сотрудника (POST /api/staff-auth/login/ по PIN + лицу): "
        "сотрудник берётся из токена, прислать время за другого нельзя. "
        "Без тела — отметка «сейчас»; либо интервал start/end. Склеивается с остальной "
        "цифровой явкой, пересечения не считаются дважды."
    ),
    tags=["Activity"],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "start": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
            "end": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
            "source": openapi.Schema(type=openapi.TYPE_STRING, description="Например: desktop"),
        },
    ),
    responses={204: "Записано", 400: "Неверный интервал", 401: "Нет/истёк токен сотрудника"},
)
@api_view(["POST"])
@authentication_classes([StaffJWTAuthentication])
@permission_classes([IsStaffToken])
def activity_ingest(request):
    data = request.data
    now = timezone.now()
    start = parse_datetime(str(data.get("start") or "")) if data.get("start") else now
    end = parse_datetime(str(data.get("end") or "")) if data.get("end") else start
    source = str(data.get("source") or "external").strip()[:32] or "external"
    if start is None or end is None or start.tzinfo is None or end.tzinfo is None:
        return Response(
            {"error": "start/end — ISO 8601 с часовым поясом"}, status=status.HTTP_400_BAD_REQUEST
        )
    too_long = (end - start).total_seconds() > MAX_INGEST_HOURS * 3600
    if end < start or too_long or end > now + FUTURE_SKEW:
        return Response(
            {"error": f"Интервал: от 0 до {MAX_INGEST_HOURS} ч и не в будущем"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    record_interval(request.user.staff.id, start, end, source)
    return Response(status=status.HTTP_204_NO_CONTENT)
