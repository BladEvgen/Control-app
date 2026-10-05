import logging
from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from monitoring_app import models

User = get_user_model()

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    date_joined = serializers.SerializerMethodField()
    last_login = serializers.SerializerMethodField()

    def get_date_joined(self, obj):
        return obj.date_joined.strftime("%Y-%m-%d %H:%M:%S") if obj.date_joined else None

    def get_last_login(self, obj):
        return obj.last_login.strftime("%Y-%m-%d %H:%M:%S") if obj.last_login else None

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "last_login",
            "is_superuser",
            "is_staff",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = models.UserProfile
        fields = [
            "user",
            "is_banned",
            "last_login_ip",
        ]

    def to_representation(self, instance):
        """
        Преобразует данные профиля пользователя в единый формат JSON,
        помещая флаги is_banned, is_superuser, is_staff и другие данные внутрь объекта user.
        Если пользователь заблокирован, возвращаются только ограниченные данные.
        """
        user_obj = instance.user

        user_data = {
            "id": user_obj.id,
            "username": user_obj.username,
            "email": user_obj.email,
            "first_name": user_obj.first_name,
            "last_name": user_obj.last_name,
            "date_joined": user_obj.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            "last_login": (
                user_obj.last_login.strftime("%Y-%m-%d %H:%M:%S") if user_obj.last_login else None
            ),
            "is_superuser": user_obj.is_superuser,
            "is_staff": user_obj.is_staff,
        }

        if not instance.is_banned:
            user_data.update(
                {
                    "phonenumber": instance.phonenumber,
                    "is_banned": instance.is_banned,
                    "last_login_ip": instance.last_login_ip,
                }
            )
        else:
            user_data = {
                "id": user_obj.id,
                "username": user_obj.username,
                "is_banned": instance.is_banned,
                "is_superuser": user_obj.is_superuser,
                "is_staff": user_obj.is_staff,
            }

        return {"user": user_data}


def get_main_parent(department):
    if department.parent is None:
        return department.id
    else:
        return get_main_parent(department.id)


class ChildDepartmentSerializer(serializers.ModelSerializer):
    child_id = serializers.CharField(source="id")
    has_child_departments = serializers.SerializerMethodField()
    direct_staff_count = serializers.SerializerMethodField()

    class Meta:
        model = models.ChildDepartment
        fields = [
            "child_id",
            "name",
            "date_of_creation",
            "parent",
            "has_child_departments",
            "direct_staff_count",
        ]

    def get_has_child_departments(self, obj) -> bool:
        child_count = getattr(obj, "annotated_child_count", None)
        if child_count is not None:
            return child_count > 0
        return models.ChildDepartment.objects.filter(parent=obj).exists()

    def get_direct_staff_count(self, obj) -> int:
        """Сотрудники, привязанные к самому отделу, без вложенных."""
        staff_count = getattr(obj, "annotated_direct_staff", None)
        if staff_count is not None:
            return staff_count
        return models.Staff.objects.filter(department=obj).count()


class AbsentReasonSerializer(serializers.ModelSerializer):
    staff = serializers.SlugRelatedField(queryset=models.Staff.objects.all(), slug_field="pin")
    reason = serializers.ChoiceField(choices=models.AbsentReason.ABSENT_REASON_CHOICES)

    class Meta:
        model = models.AbsentReason
        fields = [
            "id",
            "staff",
            "reason",
            "start_date",
            "end_date",
            "approved",
            "document",
        ]

    def __init__(self, *args, **kwargs):
        """
        Override __init__ to change the behavior of the `reason` field.

        If the passed value is not in the allowed options,

        the value "other" is returned instead of an error.
        """
        super().__init__(*args, **kwargs)
        reason_field = self.fields.get("reason")
        if reason_field is None or not hasattr(reason_field, "to_internal_value"):
            return
        original_to_internal_value = reason_field.to_internal_value

        def custom_to_internal_value(data: Any):
            try:
                return original_to_internal_value(data)
            except serializers.ValidationError:
                return "other"

        reason_field.to_internal_value = custom_to_internal_value

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        reason_display = instance.get_reason_display()
        if not reason_display:
            reason_display = "Другая причина"
        rep["reason"] = reason_display

        minimal = self.context.get("minimal_staff", False)
        if minimal:
            rep.pop("staff", None)
        else:
            staff = instance.staff
            rep["staff"] = {"pin": staff.pin, "fio": f"{staff.surname} {staff.name}"}
        return rep

    def create(self, validated_data):
        approved = validated_data.pop("approved", None)
        instance = models.AbsentReason(**validated_data)
        instance.save()
        if approved is not None:
            instance.approved = approved
            instance.save(update_fields=["approved"])
        return instance

    def update(self, instance, validated_data):
        approved = validated_data.pop("approved", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if approved is not None:
            instance.approved = approved
            instance.save(update_fields=["approved"])
        return instance


class ClassLocationSerializer(serializers.ModelSerializer):
    """Сериализатор для локаций занятий: адрес, название, радиус, широта, долгота."""

    class Meta:
        model = models.ClassLocation
        fields = [
            "id",
            "name",
            "address",
            "latitude",
            "longitude",
            "acceptance_radius_m",
        ]
        read_only_fields = ["id"]


class PublicHolidaySerializer(serializers.ModelSerializer):
    """Сериализатор праздничных дней: дата, название, рабочий ли день."""

    class Meta:
        model = models.PublicHoliday
        fields = ["id", "date", "name", "is_working_day"]
        read_only_fields = ["id"]
