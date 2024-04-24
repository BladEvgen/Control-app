from monitoring_app import models
from rest_framework import serializers


class ParentDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ParentDepartment
        fields = "__all__"


class ChildDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ChildDepartment
        fields = "__all__"


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
    class Meta:
        model = models.Salary
        fields = "__all__"
