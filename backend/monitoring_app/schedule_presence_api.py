from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from monitoring_app.models import APIKey
from monitoring_app.services.schedule_presence import schedule_presence


class SchedulePresenceBuildingSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    address = serializers.CharField(max_length=512)
    pins = serializers.ListField(
        child=serializers.RegexField(r"^[ST][0-9]+[ST]$", max_length=100), max_length=20000
    )

    def validate_pins(self, value):
        if any(pin[0] != pin[-1] for pin in value):
            raise serializers.ValidationError("PIN должен иметь одинаковую обёртку S или T.")
        return list(dict.fromkeys(value))


class SchedulePresenceRequestSerializer(serializers.Serializer):
    date = serializers.DateField()
    buildings = SchedulePresenceBuildingSerializer(many=True, allow_empty=False)

    def validate_date(self, value):
        if value >= timezone.localdate():
            raise serializers.ValidationError(
                "Фактическое посещение доступно только за прошедшие даты."
            )
        return value

    def validate_buildings(self, value):
        if len(value) > 200 or sum(len(b["pins"]) for b in value) > 30000:
            raise serializers.ValidationError("Слишком большой запрос.")
        if len({b["id"] for b in value}) != len(value):
            raise serializers.ValidationError("ID корпусов должны быть уникальны.")
        return value


class SchedulePresenceResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    address = serializers.CharField()
    status = serializers.CharField()
    present_pins = serializers.ListField(child=serializers.CharField())
    unknown_pins = serializers.ListField(child=serializers.CharField())


class SchedulePresenceResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    results = SchedulePresenceResultSerializer(many=True)


class SchedulePresenceKeyPermission(BasePermission):
    def has_permission(self, request, view):
        key = request.headers.get("X-API-KEY", "")
        return bool(key) and APIKey.objects.filter(key=key, is_active=True).exists()


class SchedulePresenceView(APIView):
    authentication_classes = []
    permission_classes = [SchedulePresenceKeyPermission]

    @swagger_auto_schema(
        operation_summary="Посещение зданий по PIN за прошедший день",
        operation_description="Вход в здание засчитывается для всех запланированных в нём занятий. Каждый PIN учитывается один раз в каждом посещённом здании. Привязка по адресу защищает от смены ID. СКУД: date_at = дата занятия + 1; геоотметки: дата занятия. Подозрительные геоотметки исключаются правилами отчёта.",
        request_body=SchedulePresenceRequestSerializer,
        responses={
            200: SchedulePresenceResponseSerializer,
            400: "Неверный запрос",
            403: "Требуется активный X-API-KEY",
        },
        tags=["Посещаемость"],
    )
    def post(self, request):
        serializer = SchedulePresenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        body = serializer.validated_data
        return Response(
            {
                "date": body["date"].isoformat(),
                "results": schedule_presence(body["date"], body["buildings"]),
            }
        )
