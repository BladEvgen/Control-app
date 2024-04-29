from monitoring_app import models
from rest_framework import serializers
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "date_joined",
            "last_login",
        ]


class UserProfileSerializer(serializers.Serializer):
    is_banned = serializers.BooleanField()
    user = UserSerializer()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["user"]["phonenumber"] = instance.phonenumber
        return data


def get_main_parent(department):
    if department.parent is None:
        return department.id
    else:
        return get_main_parent(department.id)


class ParentDepartmentSerializer(serializers.ModelSerializer):
    child_departments = serializers.SerializerMethodField()
    have_children = serializers.SerializerMethodField()

    class Meta:
        model = models.ParentDepartment
        fields = "__all__"

    def get_child_departments(self, parent_department):
        if parent_department.id == 1:
            child_departments = models.ChildDepartment.objects.all()
            return ChildDepartmentSerializer(child_departments, many=True).data
        else:
            child_departments = models.ChildDepartment.objects.filter(
                parent=parent_department
            )
            return ChildDepartmentSerializer(child_departments, many=True).data


class ChildDepartmentSerializer(serializers.ModelSerializer):
    child_id = serializers.IntegerField(source="id")

    class Meta:
        model = models.ChildDepartment
        fields = ["child_id", "name", "date_of_creation", "parent"]


class StaffSerializer(serializers.ModelSerializer):
    FIO = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()

    class Meta:
        model = models.Staff
        fields = ("pin", "FIO", "date_of_creation", "avatar", "positions")

    def get_FIO(self, obj):
        return obj.surname + " " + obj.name

    def get_positions(self, obj):
        return [position.name for position in obj.positions.all()]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return {rep["pin"]: rep}


class StaffAttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.StaffAttendance
        fields = "__all__"


class SalarySerializer(serializers.ModelSerializer):
    total_salary = serializers.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        model = models.Salary
        fields = ("total_salary",)
