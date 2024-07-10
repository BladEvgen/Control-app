from django.contrib import admin
from .models import (
    Staff,
    Salary,
    APIKey,
    Position,
    UserProfile,
    FileCategory,
    PublicHoliday,
    ChildDepartment,
    StaffAttendance,
    ParentDepartment,
)

admin.site.site_header = "Панель управления"
admin.site.index_title = "Администрирование сайта"
admin.site.site_title = "Администрирование"


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("key_name", "created_by", "created_at", "key", "is_active")
    list_filter = ("created_at", "created_by")
    search_fields = ("key_name", "created_by__username")
    ordering = ("-created_at", "key_name")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_banned", "phonenumber", "last_login_ip")
    list_filter = ("is_banned",)
    search_fields = ("user__username", "phonenumber", "last_login_ip")
    ordering = (
        "user__username",
        "-is_banned",
    )
    list_editable = ("is_banned",)


@admin.register(FileCategory)
class FileCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)


@admin.register(ParentDepartment)
class ParentDepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "date_of_creation")
    search_fields = ("name",)
    ordering = (
        "name",
        "date_of_creation",
    )


@admin.register(ChildDepartment)
class ChildDepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "date_of_creation")
    search_fields = ("name", "parent__name")
    ordering = (
        "name",
        "-date_of_creation",
    )


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "rate")
    search_fields = ("name",)
    ordering = ("-rate", "name")
    list_editable = ("rate",)


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "pin",
        "surname",
        "name",
        "department",
        "display_positions",
        "avatar",
    )
    list_filter = ("department", "positions")
    search_fields = ("surname", "name", "department__name")
    filter_horizontal = ("positions",)
    actions = ["clear_avatars"]
    ordering = (
        "surname",
        "name",
    )

    def clear_avatars(self, request, queryset):
        for staff_member in queryset:
            staff_member.avatar = None
            staff_member.save()

    clear_avatars.short_description = "Очистить фото сотрудника"

    def display_positions(self, obj):
        return ", ".join([position.name for position in obj.positions.all()])

    display_positions.short_description = "Должности"


@admin.register(StaffAttendance)
class StaffAttendanceAdmin(admin.ModelAdmin):
    list_display = ("staff", "date_at", "first_in", "last_out")
    list_filter = ("staff__department", "staff__pin", "staff__surname", "staff__name")
    search_fields = ("staff__surname", "staff__name", "staff__pin")
    date_hierarchy = "date_at"
    list_display_links = None
    ordering = ("-date_at", "-last_out", "staff")
    readonly_fields = ("first_in", "last_out")


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ("staff", "clean_salary", "dirty_salary", "total_salary")
    search_fields = ("staff__surname", "staff__name")
    list_filter = ("staff__department",)
    readonly_fields = ("dirty_salary", "total_salary")


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "is_working_day")
    list_filter = ("date", "name", "is_working_day")
    search_fields = ("name",)
    ordering = ("-date",)
