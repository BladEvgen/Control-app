from django.contrib import admin
from django.utils import timezone

from monitoring_app import utils

from .models import (
    APIKey,
    ChildDepartment,
    FileCategory,
    ParentDepartment,
    PasswordResetRequestLog,
    PasswordResetToken,
    Position,
    PublicHoliday,
    Salary,
    Staff,
    StaffAttendance,
    UserProfile,
)

admin.site.site_header = "Панель управления"
admin.site.index_title = "Администрирование сайта"
admin.site.site_title = "Администрирование"
class UsedFilter(admin.SimpleListFilter):
    title = 'Статус использования'
    parameter_name = 'used'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Использован'),
            ('no', 'Не использован'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(_used=True)
        if self.value() == 'no':
            return queryset.filter(_used=False)

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'used', 'is_valid')
    list_filter = (UsedFilter, 'created_at')
    search_fields = ('user__username', 'user__email', 'token')
    readonly_fields = ('user', 'token', 'created_at', 'used')
    list_display_links = None
    def is_valid(self, obj):
        return obj.is_valid()
    is_valid.boolean = True
    is_valid.short_description = 'Действительный токен'

@admin.register(PasswordResetRequestLog)
class PasswordResetRequestLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'requested_at', 'next_possible_request')
    list_filter = ('requested_at',)
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = ('user', 'ip_address', 'requested_at')
    list_display_links = None

    def next_possible_request(self, obj):
        return obj.requested_at + timezone.timedelta(minutes=5)
    next_possible_request.short_description = 'Следующий возможный запрос'
    
@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("key_name", "created_by", "created_at", "short_key", "is_active")
    list_filter = (
        "created_at",
        "created_by",
    )
    list_editable = ("is_active",)
    search_fields = ("key_name", "created_by__username")
    ordering = ("-created_at", "key_name")
    readonly_fields = ("key",)

    def short_key(self, obj):
        return obj.key[:8] + "..."

    short_key.short_description = "Key"

    def get_fields(self, request, obj=None):
        if obj:
            return ["key_name", "created_by", "created_at", "key", "is_active"]
        else:
            return ["key_name", "created_by", "is_active"]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["key_name", "created_by", "created_at", "key"]
        else:
            return []

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("created_by")


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


class SalaryInline(admin.TabularInline):
    model = Salary
    extra = 1
    fields = ("net_salary", "total_salary", "contract_type")
    readonly_fields = ("total_salary",)


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
    list_filter = (
        "pin",
        "department",
        "surname",
        "name",
        "positions",
    )
    search_fields = ("surname", "name", "department__name")
    filter_horizontal = ("positions",)
    actions = ["clear_avatars"]
    ordering = (
        "surname",
        "name",
    )

    inlines = [SalaryInline]

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
    list_display = ("staff", "staff_department", "date_at", "first_in", "last_out")
    list_filter = (
        utils.HierarchicalDepartmentFilter,
        "staff__pin",
        "staff__surname",
        "staff__name",
    )
    search_fields = ("staff__surname", "staff__name", "staff__pin")
    date_hierarchy = "date_at"
    list_display_links = None
    ordering = ("-date_at", "-last_out", "staff")
    readonly_fields = ("first_in", "last_out")

    def staff_department(self, obj):
        return obj.staff.department.name if obj.staff.department else "N/A"

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department__name"

    def staff_with_department(self, obj):
        return f"({obj.staff.surname} {obj.staff.name} ({obj.staff.department.name if obj.staff.department else 'N/A'})"

    staff_with_department.short_description = "Staff (Отдел)"


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ("staff", "net_salary", "total_salary")
    search_fields = ("staff__surname", "staff__name")
    list_filter = ("staff__department",)
    readonly_fields = ("total_salary",)


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "is_working_day")
    list_filter = ("date", "name", "is_working_day")
    search_fields = ("name",)
    ordering = ("-date",)
