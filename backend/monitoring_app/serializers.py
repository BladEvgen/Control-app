from monitoring_app import models
from rest_framework import serializers


class ParentDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ParentDepartment
        fields = ("id", "name", "date_of_creation")


class ChildDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ChildDepartment
        fields = ("id", "name", "date_of_creation", "parent")
