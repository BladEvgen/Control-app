import datetime
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


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = models.UserProfile
        fields = ["user", "is_banned", "phonenumber", "last_login_ip"]

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
    has_child_departments = serializers.SerializerMethodField()

    class Meta:
        model = models.ChildDepartment
        fields = [
            "child_id",
            "name",
            "date_of_creation",
            "parent",
            "has_child_departments",
        ]

    def get_has_child_departments(self, obj):
        return models.ChildDepartment.objects.filter(parent=obj).exists()


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


class StaffAttendanceDetailSerializer(serializers.Serializer):
    department = serializers.CharField(source="staff.department.name")
    staff_data = serializers.SerializerMethodField()

    def get_staff_data(self, obj):
        staff_data = {}
        if isinstance(obj, dict):
            department_id = obj["staff"].department_id
        else:
            department_id = obj.staff.department_id

        staff_attendance = models.StaffAttendance.objects.filter(
            staff__department_id=department_id
        ).order_by("-date_at")
        for attendance in staff_attendance:
            staff_fio = attendance.staff.surname + " " + attendance.staff.name
            date_at = attendance.date_at - datetime.timedelta(days=1)
            date_at_str = date_at.strftime("%Y-%m-%d")
            if staff_fio not in staff_data:
                staff_data[staff_fio] = []
            staff_data[staff_fio].append(
                {
                    "date_at": date_at_str,
                    "first_in": attendance.first_in,
                    "last_out": attendance.last_out,
                }
            )
        return staff_data

    def to_representation(self, instance):
        if isinstance(instance, dict):
            department_name = instance["staff"].department.name
        else:
            department_name = instance.staff.department.name

        return {
            "department": department_name,
            "staff_data": self.get_staff_data(instance),
        }


class StaffAttendanceByDateSerializer(serializers.Serializer):
    date = serializers.SerializerMethodField()
    staff_fio = serializers.SerializerMethodField()
    first_in = serializers.DateTimeField()
    last_out = serializers.DateTimeField()
    department = serializers.SerializerMethodField()

    def get_date(self, obj):
        return (obj.date_at - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    def get_staff_fio(self, obj):
        return f"{obj.staff.surname} {obj.staff.name}"

    def get_department(self, obj):
        return obj.staff.department.name if obj.staff.department else "N/A"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        date = data.pop("date")
        department = (
            instance.staff.department.name
            if instance.staff.department
            else "Unknown Department"
        )
        return {
            date: {
                "department": department,
                "attendance": self.context.get(date, [])
                + [
                    {
                        "staff_fio": data["staff_fio"],
                        "first_in": data["first_in"],
                        "last_out": data["last_out"],
                    }
                ],
            }
        }
