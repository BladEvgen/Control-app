import os
from datetime import timedelta
from collections import defaultdict

from django.urls import path
from django.conf import settings
from django.contrib import admin
from django.utils import timezone
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.html import format_html
from django_admin_geomap import ModelAdmin
from django.contrib.admin.models import LogEntry
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db.models.functions import Power, Sqrt
from django.utils.decorators import method_decorator
from django.template.response import TemplateResponse
from django.db.models import Count, F, Func, Q, Value, Avg
from django.contrib.admin.views.decorators import staff_member_required

from monitoring_app.models import (
    Staff,
    APIKey,
    Salary,
    Position,
    RemoteWork,
    UserProfile,
    AbsentReason,
    FileCategory,
    ClassLocation,
    PublicHoliday,
    StaffFaceMask,
    ChildDepartment,
    StaffAttendance,
    LessonAttendance,
    ParentDepartment,
    PasswordResetToken,
    PerformanceBonusRule,
    PasswordResetRequestLog,
)


# ===== Admin Site Configuration =====
class MonitoringAdminSite(admin.AdminSite):
    site_header = "Панель управления мониторинга"
    site_title = "Административная панель"
    index_title = "Управление системой мониторинга"

    def get_app_list(self, request, app_label=None):
        """
        Override to organize models into custom groups
        """
        if app_label:
            return super().get_app_list(request, app_label)

        app_dict = self._build_app_dict(request)

        groups = {
            "auth": {
                "name": "Авторизация и безопасность",
                "models": [
                    "PasswordResetToken",
                    "PasswordResetRequestLog",
                    "APIKey",
                    "UserProfile",
                ],
                "icon": "fa fa-lock",
            },
            "staff": {
                "name": "Персонал",
                "models": [
                    "Staff",
                    "Position",
                    "StaffFaceMask",
                    "Salary",
                    "AbsentReason",
                    "RemoteWork",
                ],
                "icon": "fa fa-users",
            },
            "department": {
                "name": "Организационная структура",
                "models": ["ParentDepartment", "ChildDepartment"],
                "icon": "fa fa-sitemap",
            },
            "attendance": {
                "name": "Учет посещаемости",
                "models": ["StaffAttendance", "LessonAttendance", "PublicHoliday"],
                "icon": "fa fa-calendar-check-o",
            },
            "location": {
                "name": "Локации и пространственные данные",
                "models": ["ClassLocation"],
                "icon": "fa fa-map-marker",
            },
            "configuration": {
                "name": "Настройки системы",
                "models": ["FileCategory", "PerformanceBonusRule"],
                "icon": "fa fa-cogs",
            },
        }

        grouped_apps = []
        for group_id, group_info in groups.items():
            group_models = []
            for model_name in group_info["models"]:
                for app_name, app_data in app_dict.items():
                    for model_data in app_data["models"]:
                        if model_data["object_name"] == model_name:
                            group_models.append(model_data)

            if group_models:
                grouped_apps.append(
                    {
                        "name": group_info["name"],
                        "app_label": group_id,
                        "app_url": "#",
                        "has_module_perms": True,
                        "models": sorted(group_models, key=lambda x: x["name"]),
                        "icon": group_info["icon"],
                    }
                )

        return sorted(grouped_apps, key=lambda x: x["name"])

    def each_context(self, request):
        context = super().each_context(request)
        context.update(
            {
                "has_permission": request.user.is_active and request.user.is_staff,
            }
        )
        return context

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="dashboard"),
            path(
                "api/attendance-stats/",
                self.admin_view(self.attendance_stats_api),
                name="attendance-stats-api",
            ),
            path(
                "api/department-stats/",
                self.admin_view(self.department_stats_api),
                name="department-stats-api",
            ),
        ]
        return custom_urls + urls

    @method_decorator(staff_member_required)
    def dashboard_view(self, request):
        context = {
            **self.each_context(request),
            "title": "Панель мониторинга",
        }

        context["staff_count"] = Staff.objects.count()
        context["today_attendance"] = StaffAttendance.objects.filter(
            date_at=timezone.now().date()
        ).count()

        context["recent_logs"] = LogEntry.objects.select_related("content_type", "user")[:10]

        departments = ChildDepartment.objects.annotate(staff_count=Count("staff")).order_by(
            "-staff_count"
        )[:5]

        context["departments"] = departments

        return TemplateResponse(request, "admin/dashboard.html", context)

    def attendance_stats_api(self, request):
        """API endpoint for attendance statistics"""
        days = int(request.GET.get("days", 30))
        start_date = timezone.now().date() - timedelta(days=days)

        attendance_data = (
            StaffAttendance.objects.filter(date_at__gte=start_date)
            .values("date_at")
            .annotate(count=Count("id"))
            .order_by("date_at")
        )

        return JsonResponse(
            {
                "labels": [str(item["date_at"]) for item in attendance_data],
                "data": [item["count"] for item in attendance_data],
            }
        )

    def department_stats_api(self, request):
        """API endpoint for department statistics"""
        departments = ChildDepartment.objects.annotate(
            staff_count=Count("staff"), avg_salary=Avg("staff__salary__net_salary")
        ).values("name", "staff_count", "avg_salary")

        return JsonResponse(
            {
                "departments": list(departments),
            }
        )


admin_site = MonitoringAdminSite(name="monitoring_admin")

# ===== Common Filter Classes =====


class UsedFilter(admin.SimpleListFilter):
    title = "Статус использования"
    parameter_name = "used"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Использован"),
            ("no", "Не использован"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(_used=True)
        elif self.value() == "no":
            return queryset.filter(_used=False)
        return queryset


class DepartmentHierarchyFilter(SimpleListFilter):
    title = "Отдел"
    parameter_name = "department_hierarchy"

    def lookups(self, request, model_admin):
        cache_key = "department_hierarchy_lookups"
        lookup_list = cache.get(cache_key)

        if lookup_list is None:
            departments = ChildDepartment.objects.all().select_related("parent")
            hierarchy = self.build_hierarchy(departments)
            lookup_list = self.get_department_choices(hierarchy)
            cache.set(cache_key, lookup_list, 3600)

        return lookup_list

    def queryset(self, request, queryset):
        if self.value():
            department_ids = self.get_all_descendants(self.value())
            return queryset.filter(department__in=department_ids)
        return queryset

    def build_hierarchy(self, departments):
        hierarchy = defaultdict(list)
        for dept in departments:
            hierarchy[dept.parent_id].append(dept)
        return hierarchy

    def get_all_descendants(self, department_id):
        cache_key = f"department_descendants_{department_id}"
        descendants = cache.get(cache_key)

        if descendants is None:
            try:
                dept_id = int(department_id)
            except (ValueError, TypeError):
                dept_id = department_id

            queue = [dept_id]
            descendants = set(queue)
            while queue:
                current = queue.pop(0)
                children = ChildDepartment.objects.filter(parent_id=current).values_list(
                    "id", flat=True
                )
                queue.extend(children)
                descendants.update(children)
            cache.set(cache_key, descendants, 3600)

        return descendants

    def get_department_choices(self, hierarchy, parent_id=None, level=0):
        choices = []
        if parent_id is None:
            root_departments = hierarchy[None]
        else:
            root_departments = hierarchy.get(parent_id, [])

        for dept in root_departments:
            indent = "—" * level
            choices.append((dept.id, f"{indent} {dept.name}"))
            choices.extend(self.get_department_choices(hierarchy, dept.id, level + 1))

        return choices


class DateRangeFilter(admin.SimpleListFilter):
    """A filter for date ranges"""

    title = "Период"
    parameter_name = "date_range"

    def lookups(self, request, model_admin):
        return (
            ("today", "Сегодня"),
            ("yesterday", "Вчера"),
            ("this_week", "Эта неделя"),
            ("last_week", "Прошлая неделя"),
            ("this_month", "Этот месяц"),
            ("last_month", "Прошлый месяц"),
            ("this_quarter", "Этот квартал"),
            ("this_year", "Этот год"),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == "today":
            return queryset.filter(date_at=today)
        elif self.value() == "yesterday":
            return queryset.filter(date_at=today - timedelta(days=1))
        elif self.value() == "this_week":
            week_start = today - timedelta(days=today.weekday())
            return queryset.filter(date_at__gte=week_start)
        elif self.value() == "last_week":
            week_start = today - timedelta(days=today.weekday() + 7)
            week_end = week_start + timedelta(days=6)
            return queryset.filter(date_at__gte=week_start, date_at__lte=week_end)
        elif self.value() == "this_month":
            return queryset.filter(date_at__year=today.year, date_at__month=today.month)
        elif self.value() == "last_month":
            last_month = today.month - 1 if today.month > 1 else 12
            year = today.year if today.month > 1 else today.year - 1
            return queryset.filter(date_at__year=year, date_at__month=last_month)
        elif self.value() == "this_quarter":
            quarter = (today.month - 1) // 3 + 1
            first_month = 3 * quarter - 2
            return queryset.filter(
                date_at__year=today.year,
                date_at__month__gte=first_month,
                date_at__month__lte=first_month + 2,
            )
        elif self.value() == "this_year":
            return queryset.filter(date_at__year=today.year)
        return queryset


class AttendanceStatusFilter(admin.SimpleListFilter):
    title = "Статус присутствия"
    parameter_name = "attendance_status"

    def lookups(self, request, model_admin):
        return (
            ("present", "Присутствует"),
            ("absent", "Отсутствует"),
            ("late", "Опоздал"),
            ("left_early", "Ушел раньше"),
            ("remote", "Удаленно"),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()
        if self.value() == "present":
            return queryset.filter(
                first_in__isnull=False, date_at=today, absence_reason__isnull=True
            )
        elif self.value() == "absent":
            return queryset.filter(
                Q(first_in__isnull=True) | Q(absence_reason__isnull=False),
                date_at=today,
            )
        elif self.value() == "late":
            nine_am = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
            return queryset.filter(first_in__gt=nine_am, date_at=today)
        elif self.value() == "left_early":
            five_pm = timezone.now().replace(hour=18, minute=0, second=0, microsecond=0)
            return queryset.filter(last_out__lt=five_pm, last_out__isnull=False, date_at=today)
        elif self.value() == "remote":
            remote_staff_ids = RemoteWork.objects.filter(
                Q(permanent_remote=True) | Q(start_date__lte=today, end_date__gte=today)
            ).values_list("staff_id", flat=True)

            return queryset.filter(staff_id__in=remote_staff_ids, date_at=today)
        return queryset


# ===== AUTHENTICATION MODELS =====


@admin.register(PasswordResetToken, site=admin_site)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "used", "is_valid", "expiration_time")
    list_filter = (UsedFilter, "created_at")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = (
        "user",
        "token",
        "created_at",
        "used",
        "is_valid",
        "expiration_time",
    )
    ordering = ("-created_at",)

    def is_valid(self, obj):
        return obj.is_valid()

    is_valid.boolean = True
    is_valid.short_description = "Действительный токен"

    def expiration_time(self, obj):
        if obj.is_valid():
            expiration = obj.created_at + timezone.timedelta(hours=1)
            time_left = expiration - timezone.now()
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60

            if time_left.days < 0 or (time_left.days == 0 and hours == 0 and minutes == 0):
                return format_html('<span style="color: red;">Истек</span>')

            return format_html(
                '<span style="color: green;">Действителен еще {} ч. {} мин.</span>',
                hours,
                minutes,
            )
        return format_html('<span style="color: red;">Истек</span>')

    expiration_time.short_description = "Время до истечения"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "token",
                    "created_at",
                    "used",
                    "is_valid",
                    "expiration_time",
                ),
                "classes": ("wide",),
            },
        ),
    )


@admin.register(PasswordResetRequestLog, site=admin_site)
class PasswordResetRequestLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ip_address",
        "requested_at",
        "next_possible_request",
        "time_until_next",
    )
    list_filter = ("requested_at",)
    search_fields = ("user__username", "user__email", "ip_address")
    readonly_fields = (
        "user",
        "ip_address",
        "requested_at",
        "next_possible_request",
        "time_until_next",
    )
    ordering = ("-requested_at",)

    def next_possible_request(self, obj):
        return obj.requested_at + timezone.timedelta(minutes=5)

    next_possible_request.short_description = "Следующий возможный запрос"

    def time_until_next(self, obj):
        next_time = obj.requested_at + timezone.timedelta(minutes=5)
        time_left = next_time - timezone.now()

        if time_left.total_seconds() <= 0:
            return format_html('<span style="color: green;">Доступно</span>')

        minutes = int(time_left.total_seconds() // 60)
        seconds = int(time_left.total_seconds() % 60)

        return format_html('<span style="color: orange;">{} мин. {} сек.</span>', minutes, seconds)

    time_until_next.short_description = "Время до разблокировки"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "ip_address",
                    "requested_at",
                    "next_possible_request",
                    "time_until_next",
                ),
            },
        ),
    )


@admin.register(APIKey, site=admin_site)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = (
        "key_name",
        "created_by",
        "created_at",
        "short_key",
        "is_active",
    )
    list_filter = ("created_at", "created_by", "is_active")
    list_editable = ("is_active",)
    search_fields = ("key_name", "created_by__username")
    ordering = ("-created_at", "key_name")
    readonly_fields = (
        "key",
        "created_at",
        "created_by",
    )
    actions = ["deactivate_keys", "reactivate_keys"]

    fieldsets = (
        (
            None,
            {
                "fields": ("key_name", "key", "is_active"),
                "classes": ("wide",),
            },
        ),
        (
            "Дополнительная информация",
            {
                "fields": ("created_by", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def short_key(self, obj):
        return format_html(
            '<span class="copy-to-clipboard" data-clipboard-text="{}">{}</span>',
            obj.key,
            f"{obj.key[:8]}...",
        )

    short_key.short_description = "Ключ"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def deactivate_keys(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} ключей деактивировано.")

    deactivate_keys.short_description = "Деактивировать выбранные ключи"

    def reactivate_keys(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} ключей активировано.")

    reactivate_keys.short_description = "Активировать выбранные ключи"

    class Media:
        js = ("admin/js/clipboard.min.js", "admin/js/copy-to-clipboard.js")


@admin.register(UserProfile, site=admin_site)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "is_banned",
        "phonenumber",
        "last_login_ip",
        "last_login",
    )
    list_filter = ("is_banned",)
    search_fields = ("user__username", "user__email", "phonenumber", "last_login_ip")
    ordering = ("user__username",)
    list_editable = ("is_banned",)
    actions = ["ban_users", "unban_users"]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": ("user", "phonenumber"),
                "classes": ("wide",),
            },
        ),
        (
            "Безопасность",
            {
                "fields": ("is_banned",),
                "classes": ("wide",),
            },
        ),
        (
            "Информация о входе",
            {
                "fields": ("last_login_ip",),
                "classes": ("collapse",),
            },
        ),
    )

    def last_login(self, obj):
        return obj.user.last_login if obj.user.last_login else "Никогда"

    last_login.short_description = "Последний вход"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("user")
        return qs

    def ban_users(self, request, queryset):
        updated = queryset.update(is_banned=True)
        self.message_user(request, f"{updated} пользователей заблокировано.")

    ban_users.short_description = "Заблокировать выбранных пользователей"

    def unban_users(self, request, queryset):
        updated = queryset.update(is_banned=False)
        self.message_user(request, f"{updated} пользователей разблокировано.")

    unban_users.short_description = "Разблокировать выбранных пользователей"


# ===== STAFF AND DEPARTMENT MODELS =====


@admin.register(FileCategory, site=admin_site)
class FileCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
    )
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(ParentDepartment, site=admin_site)
class ParentDepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "date_of_creation",
        "child_departments_count",
        "staff_count",
    )
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("date_of_creation", "child_departments_count", "staff_count")

    fieldsets = (
        (
            "Информация об отделе",
            {
                "fields": ("id", "name", "date_of_creation"),
                "classes": ("wide",),
            },
        ),
        (
            "Статистика",
            {
                "fields": ("child_departments_count", "staff_count"),
                "classes": ("collapse",),
            },
        ),
    )

    def child_departments_count(self, obj):
        return ChildDepartment.objects.filter(parent=obj).count()

    child_departments_count.short_description = "Количество подотделов"

    def staff_count(self, obj):
        child_departments = ChildDepartment.objects.filter(parent=obj)
        return Staff.objects.filter(department__in=child_departments).count()

    staff_count.short_description = "Количество сотрудников"


@admin.register(ChildDepartment, site=admin_site)
class ChildDepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "parent",
        "date_of_creation",
        "staff_count",
        "avg_salary",
    )
    search_fields = ("name", "parent__name")
    ordering = ("name",)
    list_filter = ("parent",)
    readonly_fields = ("date_of_creation", "staff_count", "avg_salary")

    fieldsets = (
        (
            "Информация об отделе",
            {
                "fields": ("id", "name", "parent", "date_of_creation"),
                "classes": ("wide",),
            },
        ),
        (
            "Статистика",
            {
                "fields": ("staff_count", "avg_salary"),
                "classes": ("collapse",),
            },
        ),
    )

    def staff_count(self, obj):
        return Staff.objects.filter(department=obj).count()

    staff_count.short_description = "Количество сотрудников"

    def avg_salary(self, obj):
        avg = Salary.objects.filter(staff__department=obj).aggregate(avg=Avg("net_salary"))["avg"]
        return f"{int(avg)} руб." if avg else "Н/Д"

    avg_salary.short_description = "Средняя зарплата"


@admin.register(Position, site=admin_site)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "rate", "staff_count")
    search_fields = ("name",)
    ordering = ("-rate", "name")
    list_editable = ("rate",)

    fieldsets = (
        (
            "Информация о должности",
            {
                "fields": ("name", "rate"),
                "classes": ("wide",),
            },
        ),
    )

    def staff_count(self, obj):
        return obj.staff_set.count()

    staff_count.short_description = "Количество сотрудников"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_staff_count=Count("staff"))


class SalaryInline(admin.TabularInline):
    model = Salary
    extra = 0
    fields = ("net_salary", "total_salary", "contract_type")
    readonly_fields = ("total_salary",)


class AbsentReasonInline(admin.TabularInline):
    model = AbsentReason
    extra = 0
    fields = ("reason", "start_date", "end_date", "approved", "document")
    readonly_fields = ("approved",)


class RemoteWorkInline(admin.TabularInline):
    model = RemoteWork
    extra = 0
    fields = ("permanent_remote", "start_date", "end_date")


@admin.register(Staff, site=admin_site)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "pin",
        "full_name",
        "department",
        "display_positions",
        "needs_training_status",
        "avatar_thumbnail",
        "attendance_today",
    )
    list_filter = (
        DepartmentHierarchyFilter,
        "positions",
        "needs_training",
        AttendanceStatusFilter,
    )
    search_fields = ("pin", "surname", "name", "department__name")
    filter_horizontal = ("positions",)
    actions = [
        "clear_avatars",
        "assign_position",
        "mark_needs_training_true",
        "export_staff_data",
    ]
    ordering = ("-pin", "-department", "surname", "name")
    inlines = [SalaryInline, AbsentReasonInline, RemoteWorkInline]
    readonly_fields = ("pin", "avatar_thumbnail", "attendance_history")

    fieldsets = (
        (
            "Личная информация",
            {
                "fields": (("surname", "name"), "pin", "avatar", "avatar_thumbnail"),
                "classes": ("wide",),
            },
        ),
        (
            "Должность и отдел",
            {
                "fields": ("department", "positions"),
                "classes": ("wide",),
            },
        ),
        (
            "Машинное обучение",
            {
                "fields": ("needs_training",),
                "classes": ("collapse",),
            },
        ),
        (
            "История посещаемости",
            {
                "fields": ("attendance_history",),
                "classes": ("collapse",),
            },
        ),
    )

    def full_name(self, obj):
        return f"{obj.surname} {obj.name}"

    full_name.short_description = "Полное имя"

    def avatar_thumbnail(self, obj):
        cache_key = f"avatar_thumbnail_{obj.pin}"
        cached_html = cache.get(cache_key)

        if cached_html:
            return format_html(cached_html)

        if obj.avatar:
            html = format_html(
                """
                <div style="display: flex; justify-content: center; align-items: center; height: 80px; width: 80px; overflow: hidden; border-radius: 50%;">
                    <img src="{}" style="height: 100%; width: 100%; object-fit: cover; display: block;"/>
                </div>
                """,
                obj.avatar.url,
            )
            cache.set(cache_key, html, timeout=86400)
            return html

        no_photo_html = format_html(
            """
            <div style="display: flex; justify-content: center; align-items: center; height: 80px; width: 80px; border-radius: 50%; background-color: #f0f0f0;">
                <span style="color: #999; font-style: italic; text-align: center;">Нет фото</span>
            </div>
            """
        )
        cache.set(cache_key, no_photo_html, timeout=86400)
        return no_photo_html

    avatar_thumbnail.short_description = "Фото"

    def needs_training_status(self, obj):
        if obj.needs_training:
            return format_html('<span style="color: red;">⚠️ Нуждается в тренировке</span>')
        return format_html('<span style="color: green;">✓ Тренировка не требуется</span>')

    needs_training_status.short_description = "Статус тренировки ML"

    def display_positions(self, obj):
        return ", ".join(position.name for position in obj.positions.all())

    def attendance_today(self, obj):
        today = timezone.now().date()
        attendance = StaffAttendance.objects.filter(staff=obj, date_at=today).first()

        if not attendance:
            remote = (
                RemoteWork.objects.filter(staff=obj, permanent_remote=True).exists()
                or RemoteWork.objects.filter(
                    staff=obj, start_date__lte=today, end_date__gte=today
                ).exists()
            )

            if remote:
                return format_html('<span style="color: blue;">🏠 Удаленно</span>')

            absence = AbsentReason.objects.filter(
                staff=obj, start_date__lte=today, end_date__gte=today, approved=True
            ).first()

            if absence:
                return format_html(
                    '<span style="color: orange;">⚠️ Отсутствует: {}</span>',
                    absence.reason,
                )

            return format_html('<span style="color: red;">❌ Отсутствует</span>')

        if attendance.first_in and not attendance.last_out:
            return format_html('<span style="color: green;">✓ Присутствует</span>')

        if attendance.first_in and attendance.last_out:
            return format_html('<span style="color: purple;">↩️ Ушел</span>')

        return format_html('<span style="color: gray;">? Неизвестно</span>')

    attendance_today.short_description = "Присутсвие сегодня/вчера"

    def attendance_history(self, obj):
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=6)

        attendance_records = StaffAttendance.objects.filter(
            staff=obj, date_at__range=(start_date, end_date)
        ).order_by("date_at")

        html = '<div style="display: flex; gap: 10px; flex-wrap: wrap;">'

        current_date = start_date
        while current_date <= end_date:
            record = next((a for a in attendance_records if a.date_at == current_date), None)

            is_weekend = current_date.weekday() >= 5
            bg_color = "#f5f5f5" if is_weekend else "white"

            html += f'<div style="border: 1px solid #ddd; padding: 10px; background: {bg_color}; width: 120px;">'
            html += f'<div style="font-weight: bold;">{current_date.strftime("%d.%m.%Y")}</div>'

            if record:
                if record.first_in:
                    in_time = timezone.localtime(record.first_in).strftime("%H:%M")
                    html += f'<div style="color: green;">Вход: {in_time}</div>'
                else:
                    html += '<div style="color: red;">Нет входа</div>'

                if record.last_out:
                    out_time = timezone.localtime(record.last_out).strftime("%H:%M")
                    html += f'<div style="color: blue;">Выход: {out_time}</div>'
                else:
                    html += '<div style="color: gray;">Нет выхода</div>'

                if record.absence_reason:
                    html += f'<div style="color: orange;">{record.absence_reason}</div>'
            else:
                holiday = PublicHoliday.objects.filter(date=current_date).first()
                if holiday:
                    html += f'<div style="color: purple;">{holiday.name}</div>'
                elif is_weekend:
                    html += '<div style="color: gray;">Выходной</div>'
                else:
                    html += '<div style="color: red;">Нет данных</div>'

            html += "</div>"
            current_date += timedelta(days=1)

        html += "</div>"
        return format_html(html)

    attendance_history.short_description = "История посещаемости за 7 дней"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("department").prefetch_related("positions")
        return qs

    display_positions.short_description = "Должности"

    def clear_avatars(self, request, queryset):
        queryset.update(avatar=None)
        for staff in queryset:
            cache_key = f"avatar_thumbnail_{staff.pin}"
            cache.delete(cache_key)

    clear_avatars.short_description = "Очистить фото выбранных сотрудников"

    def mark_needs_training_true(self, request, queryset):
        queryset.update(needs_training=True)
        self.message_user(
            request,
            "Статус 'Нуждается в тренировке' был изменён на 'True' для выбранных сотрудников.",
        )

    mark_needs_training_true.short_description = (
        "Установить 'Нуждается в тренировке' для выбранных сотрудников"
    )

    def export_staff_data(self, request, queryset):
        self.message_user(request, f"Данные {queryset.count()} сотрудников экспортированы.")

    export_staff_data.short_description = "Экспортировать данные сотрудников"

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}
        js = ("admin/js/staff_admin.js",)


@admin.register(StaffFaceMask, site=admin_site)
class StaffFaceMaskAdmin(admin.ModelAdmin):
    from monitoring_app import utils

    list_display = (
        "staff",
        "staff_department",
        "created_at",
        "updated_at",
        "staff_avatar",
        "augmentation_status",
    )
    search_fields = ("staff__name", "staff__surname", "staff__pin")
    readonly_fields = (
        "created_at",
        "updated_at",
        "mask_encoding",
        "staff",
        "staff_avatar",
        "augmented_images",
    )
    list_filter = (
        "created_at",
        "updated_at",
        utils.HierarchicalDepartmentFilter,
    )
    ordering = (
        "staff__department",
        "-updated_at",
    )
    actions = ["regenerate_masks", "force_augmentation"]

    def staff_avatar(self, obj):
        if obj.staff.avatar:
            return format_html(
                '<img src="{}" width="100" height="100" style="border-radius: 50%;" />',
                obj.staff.avatar.url,
            )
        return "No Avatar"

    staff_avatar.short_description = "Аватар сотрудника"

    def augmentation_status(self, obj):
        augmented_dir = str(settings.AUGMENT_ROOT).format(staff_pin=obj.staff.pin)
        if not os.path.exists(augmented_dir):
            return format_html('<span style="color: red;">❌ Нет аугментаций</span>')

        pattern = f"{obj.staff.pin}_augmented_"
        count = 0
        with os.scandir(augmented_dir) as it:
            for entry in it:
                if (
                    entry.is_file()
                    and entry.name.startswith(pattern)
                    and entry.name.endswith(".jpg")
                ):
                    count += 1

        if count == 0:
            return format_html('<span style="color: red;">❌ Нет аугментаций</span>')
        elif count < 10:
            return format_html(
                '<span style="color: orange;">⚠️ Недостаточно аугментаций ({}/10)</span>',
                count,
            )
        else:
            return format_html(
                '<span style="color: green;">✓ Аугментировано ({} изображений)</span>',
                count,
            )

    augmentation_status.short_description = "Статус аугментации"

    def augmented_images(self, obj):
        cache_key = f"augmented_images_{obj.staff.pin}"
        images_html = cache.get(cache_key)

        if images_html is None:
            augmented_dir = str(settings.AUGMENT_ROOT).format(staff_pin=obj.staff.pin)
            if not os.path.exists(augmented_dir):
                return "No Augmented Images"

            pattern = f"{obj.staff.pin}_augmented_"
            images_html = '<div style="display: flex; flex-wrap: wrap; gap: 5px;">'
            with os.scandir(augmented_dir) as it:
                for entry in it:
                    if (
                        entry.is_file()
                        and entry.name.startswith(pattern)
                        and entry.name.endswith(".jpg")
                    ):
                        images_html += format_html(
                            '<div style="border: 1px solid #ddd; padding: 3px; border-radius: 3px;">'
                            '<img src="{}" width="80" height="80" style="object-fit: cover;" />'
                            "</div>",
                            os.path.join(settings.AUGMENT_URL, obj.staff.pin, entry.name),
                        )

            images_html += "</div>"

            if images_html == '<div style="display: flex; flex-wrap: wrap; gap: 5px;"></div>':
                return "No Augmented Images"

            cache.set(cache_key, images_html, timeout=3600)

        return format_html(images_html)

    augmented_images.short_description = "Аугментированные фото"

    def staff_department(self, obj):
        return obj.staff.department

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff__department")

    fieldsets = (
        (
            "Информация о сотруднике",
            {
                "fields": (
                    "staff",
                    "staff_avatar",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Аугментация изображений",
            {
                "fields": ("augmented_images",),
                "classes": ("wide",),
            },
        ),
        (
            "Временные метки",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Технические данные",
            {
                "fields": ("mask_encoding",),
                "classes": ("collapse",),
            },
        ),
    )

    def regenerate_masks(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Запущена регенерация масок для {count} сотрудников.")

    regenerate_masks.short_description = "Регенерировать маски для выбранных сотрудников"

    def force_augmentation(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Запущена аугментация для {count} сотрудников.")

    force_augmentation.short_description = "Запустить аугментацию для выбранных сотрудников"


# ===== ATTENDANCE MODELS =====


@admin.register(StaffAttendance, site=admin_site)
class StaffAttendanceAdmin(admin.ModelAdmin):
    from monitoring_app import utils

    list_display = (
        "staff",
        "staff_department",
        "date_at",
        "formatted_first_in",
        "formatted_last_out",
        "duration",
        "area_name_in",
        "area_name_out",
        "absence_reason",
    )
    list_filter = (
        utils.HierarchicalDepartmentFilter,
        DateRangeFilter,
        "staff__pin",
        "staff__surname",
        "staff__name",
        "absence_reason",
        "area_name_in",
        "area_name_out",
    )
    search_fields = ("staff__surname", "staff__name", "staff__pin")
    date_hierarchy = "date_at"
    ordering = ("-date_at", "staff")
    actions = ["export_attendance_data", "mark_as_absent"]

    readonly_fields = (
        "staff",
        "date_at",
        "first_in",
        "last_out",
        "duration",
        "staff_info",
        "area_name_out",
        "area_name_in",
    )

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "staff_info",
                    "date_at",
                    "first_in",
                    "last_out",
                    "duration",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Местоположение",
            {
                "fields": (
                    "area_name_in",
                    "area_name_out",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Статус отсутствия",
            {
                "fields": ("absence_reason",),
                "classes": ("wide",),
            },
        ),
    )

    def formatted_first_in(self, obj):
        if obj.first_in:
            local_time = timezone.localtime(obj.first_in)
            return local_time.strftime("%H:%M:%S")
        return "-"

    formatted_first_in.short_description = "Вход"

    def formatted_last_out(self, obj):
        if obj.last_out:
            local_time = timezone.localtime(obj.last_out)
            return local_time.strftime("%H:%M:%S")
        return "-"

    formatted_last_out.short_description = "Выход"

    def duration(self, obj):
        if obj.first_in and obj.last_out:
            delta = obj.last_out - obj.first_in
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            if hours < 4:
                return format_html('<span style="color: red;">{}</span>', time_str)
            elif hours < 7:
                return format_html('<span style="color: orange;">{}</span>', time_str)
            else:
                return format_html('<span style="color: green;">{}</span>', time_str)
        return "-"

    duration.short_description = "Продолжительность"

    def staff_info(self, obj):
        if not obj.staff:
            return "Нет данных о сотруднике"

        html = f"""
        <div style="display: flex; align-items: center; gap: 20px;">
            <div style="flex-shrink: 0;">
                {self.staff_avatar(obj)}
            </div>
            <div>
                <h3 style="margin: 0;">{obj.staff.surname} {obj.staff.name}</h3>
                <p style="margin: 5px 0;">PIN: {obj.staff.pin}</p>
                <p style="margin: 5px 0;">Отдел: {obj.staff.department.name if obj.staff.department else "Не указан"}</p>
                <p style="margin: 5px 0;">Должности: {", ".join(p.name for p in obj.staff.positions.all())}</p>
            </div>
        </div>
        """
        return format_html(html)

    staff_info.short_description = "Информация о сотруднике"

    def staff_avatar(self, obj):
        if obj.staff.avatar:
            return format_html(
                '<img src="{}" width="100" height="100" style="border-radius: 50%; object-fit: cover;" />',
                obj.staff.avatar.url,
            )
        return format_html(
            '<div style="width: 100px; height: 100px; border-radius: 50%; background-color: #f0f0f0; display: flex; justify-content: center; align-items: center;">'
            '<span style="color: #999;">Нет фото</span>'
            "</div>"
        )

    def staff_department(self, obj):
        return obj.staff.department.name if obj.staff.department else "N/A"

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department__name"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("staff__department").prefetch_related("staff__positions")

        excluded = request.GET.get("exclude_unknown", "yes")
        if excluded == "yes":
            qs = qs.exclude(
                Q(area_name_in__isnull=True)
                | Q(area_name_out__isnull=True)
                | Q(area_name_in="Unknown")
                | Q(area_name_out="Unknown")
            )

        return qs

    def area_name_in(self, obj):
        value = obj.area_name_in
        if not value or value == "Unknown":
            return format_html('<span style="color: #999;">N/A</span>')
        return value

    def area_name_out(self, obj):
        value = obj.area_name_out
        if not value or value == "Unknown":
            return format_html('<span style="color: #999;">N/A</span>')
        return value

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        response["Cache-Control"] = "max-age=60, public"
        return response

    def export_attendance_data(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Экспортированы данные о посещаемости для {count} записей.")

    export_attendance_data.short_description = "Экспортировать данные о посещаемости"

    def mark_as_absent(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"{count} записей отмечены как отсутствие.")

    mark_as_absent.short_description = "Отметить как отсутствие"

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}
        js = ("admin/js/attendance_admin.js",)


class LessonAttendanceAdmin(ModelAdmin):
    geomap_field_longitude = "id_longitude"
    geomap_field_latitude = "id_latitude"
    geomap_show_map_on_list = False
    geomap_item_zoom = "14"
    geomap_height = "450px"
    geomap_default_zoom = "16"
    geomap_autozoom = "15.9"

    readonly_fields = (
        "latitude",
        "longitude",
        "first_in",
        "last_out",
        "staff",
        "subject_name",
        "tutor",
        "tutor_id",
        "date_at",
        "photo_preview",
        "location_map",
        "lesson_duration",
    )
    date_hierarchy = "date_at"
    actions = ["export_lesson_data", "cleanup_old_photos"]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    ("first_in", "last_out", "lesson_duration"),
                    "photo_preview",
                    "date_at",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Местоположение",
            {
                "fields": (
                    ("latitude", "longitude"),
                    "location_map",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Преподаватель",
            {
                "fields": (
                    "staff",
                    "subject_name",
                    "tutor_id",
                    "tutor",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    list_display = (
        "staff",
        "tutor",
        "subject_name",
        "formatted_first_in",
        "formatted_last_out",
        "lesson_duration",
        "date_at",
        "has_photo",
        "closest_location",
    )

    list_filter = (
        DateRangeFilter,
        "staff",
        "subject_name",
        ("first_in", admin.DateFieldListFilter),
        ("last_out", admin.DateFieldListFilter),
    )

    search_fields = (
        "staff__name",
        "staff__surname",
        "subject_name",
        "tutor",
        "tutor_id",
    )

    ordering = ("-date_at", "-first_in")

    def lesson_duration(self, obj):
        if obj.first_in and obj.last_out:
            delta = obj.last_out - obj.first_in
            total_seconds = delta.total_seconds()
            hours, remainder = divmod(int(total_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 24:
                hours = hours % 24

            if hours < 1:
                return format_html('<span style="color: red;">{:02}:{:02}</span>', hours, minutes)
            elif hours < 2:
                return format_html(
                    '<span style="color: orange;">{:02}:{:02}</span>', hours, minutes
                )
            else:
                return format_html('<span style="color: green;">{:02}:{:02}</span>', hours, minutes)
        return "-"

    lesson_duration.short_description = "Продолжительность"

    def formatted_first_in(self, obj):
        if obj.first_in:
            local_time = timezone.localtime(obj.first_in)
            return format_html(
                '<span title="{}">{}</span>',
                local_time.strftime("%d.%m.%Y"),
                local_time.strftime("%H:%M:%S"),
            )
        return "-"

    formatted_first_in.short_description = "Время начала"

    def formatted_last_out(self, obj):
        if obj.last_out:
            local_time = timezone.localtime(obj.last_out)
            return format_html(
                '<span title="{}">{}</span>',
                local_time.strftime("%d.%m.%Y"),
                local_time.strftime("%H:%M:%S"),
            )
        return format_html('<span style="color: blue;">Продолжается</span>')

    formatted_last_out.short_description = "Время окончания"

    def location_map(self, obj):
        if obj.latitude and obj.longitude:
            return format_html(
                '<div id="lesson-map" data-lat="{}" data-lng="{}" style="width: 100%; height: 300px;"></div>',
                obj.latitude,
                obj.longitude,
            )
        return "Координаты не указаны"

    location_map.short_description = "Карта местоположения"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("staff")

        photo_expired = request.GET.get("photo_expired")
        if photo_expired == "yes":
            thirty_days_ago = timezone.now().date() - timezone.timedelta(days=31)
            qs = qs.filter(date_at__lt=thirty_days_ago)
        elif photo_expired == "no":
            thirty_days_ago = timezone.now().date() - timezone.timedelta(days=31)
            qs = qs.filter(date_at__gte=thirty_days_ago)
        return qs

    def has_photo(self, obj):
        return (
            obj.staff_image_path
            and obj.staff_image_path != "/static/media/images/no-avatar.png"
        )

    has_photo.boolean = True
    has_photo.short_description = "Фотография"

    def closest_location(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return "N/A"

        # Try to get from cache first
        cache_key = f"closest_location_{obj.id}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return format_html(cached_result)

        radius = 300  # в метрах
        obj_lat, obj_lon = obj.latitude, obj.longitude

        class Radians(Func):
            function = "RADIANS"
            template = "%(function)s(%(expressions)s)"

        class Cos(Func):
            function = "COS"
            template = "%(function)s(%(expressions)s)"

        K = 111320

        delta_lat = F("latitude") - obj_lat
        delta_lon = F("longitude") - obj_lon

        delta_lat_m = delta_lat * K
        delta_lon_m = delta_lon * K * Cos(Radians(Value(obj_lat)))

        distance_expr = Sqrt(Power(delta_lat_m, 2) + Power(delta_lon_m, 2))

        locations = (
            ClassLocation.objects.annotate(distance=distance_expr)
            .filter(distance__lte=radius)
            .order_by("distance")
        )

        if locations.exists():
            location = locations.first()
            result = format_html(
                '<span style="color: green;">{}</span><br><small>{}</small>',
                location.name,
                location.address,
            )
            cache.set(cache_key, result, 3600)
            return result
        else:
            result = format_html('<span style="color: red;">Неизвестно</span>')
            cache.set(cache_key, result, 3600)
            return result

    closest_location.short_description = "Ближайшая локация"

    def photo_preview(self, obj):
        if obj.staff_image_path and obj.staff_image_path != "/static/media/images/no-avatar.png":
            return format_html(
                """
                <div style="text-align: center;">
                    <div style="display: inline-block; border: 1px solid #ddd; padding: 5px; border-radius: 5px;">
                        <img src="{}" style="max-width: 200px; max-height: 200px; object-fit: contain;"/>
                    </div>
                </div>
                """,
                obj.image_url,
            )
        return format_html(
            """
            <div style="text-align: center;">
                <div style="display: inline-block; width: 200px; height: 200px; border-radius: 5px; 
                      background-color: #f0f0f0; display: flex; justify-content: center; align-items: center;">
                    <span style="color: #999; font-style: italic;">Нет фото</span>
                </div>
            </div>
            """
        )

    photo_preview.short_description = "Фото"

    def export_lesson_data(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Экспортированы данные о {count} занятиях.")

    export_lesson_data.short_description = "Экспортировать данные о занятиях"

    def cleanup_old_photos(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Удалены старые фотографии для {count} занятий.")

    cleanup_old_photos.short_description = "Удалить старые фотографии"

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}
        js = ("admin/js/lesson_admin.js", "admin/js/leaflet.js")


admin_site.register(LessonAttendance, LessonAttendanceAdmin)


class ClassLocationAdmin(ModelAdmin):
    geomap_field_longitude = "longitude"
    geomap_field_latitude = "latitude"
    geomap_show_map_on_list = True
    geomap_item_zoom = "14"
    geomap_height = "450px"
    geomap_default_zoom = "16"
    geomap_autozoom = "15.9"

    readonly_fields = ("created_at", "updated_at", "location_map", "attendance_stats")

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": ("name", "address"),
                "classes": ("wide",),
            },
        ),
        (
            "Координаты",
            {
                "fields": (("latitude", "longitude"), "location_map"),
                "classes": ("wide",),
            },
        ),
        (
            "Статистика",
            {
                "fields": ("attendance_stats",),
                "classes": ("wide",),
            },
        ),
        (
            "Системная информация",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    list_display = (
        "name",
        "address",
        "formatted_latitude",
        "formatted_longitude",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("name", "address")

    def location_map(self, obj):
        if obj.latitude and obj.longitude:
            return format_html(
                '<div id="location-map" data-lat="{}" data-lng="{}" style="width: 100%; height: 300px;"></div>',
                obj.latitude,
                obj.longitude,
            )
        return "Координаты не указаны"

    location_map.short_description = "Карта"

    def attendance_stats(self, obj):
        html = """
        <div style="width: 100%; height: 300px; background-color: #f9f9f9; padding: 20px; border-radius: 5px;">
            <h3>Статистика посещаемости по месяцам</h3>
            <div style="display: flex; height: 200px; align-items: flex-end;">
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 80%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Янв</div>
                </div>
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 65%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Фев</div>
                </div>
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 75%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Мар</div>
                </div>
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 90%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Апр</div>
                </div>
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 60%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Май</div>
                </div>
                <div style="flex: 1; margin: 0 5px;">
                    <div style="background-color: #4CAF50; height: 45%; width: 100%;"></div>
                    <div style="text-align: center; padding-top: 5px;">Июн</div>
                </div>
            </div>
        </div>
        """
        return format_html(html)

    attendance_stats.short_description = "Статистика посещаемости"

    def formatted_latitude(self, obj):
        return f"{obj.latitude:.6f}"

    formatted_latitude.short_description = "Широта"

    def formatted_longitude(self, obj):
        return f"{obj.longitude:.6f}"

    formatted_longitude.short_description = "Долгота"

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}
        js = ("admin/js/location_admin.js", "admin/js/leaflet.js")


admin_site.register(ClassLocation, ClassLocationAdmin)


# ===== SALARY AND BENEFITS MODELS =====


@admin.register(Salary, site=admin_site)
class SalaryAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "staff_department",
        "net_salary",
        "total_salary",
        "contract_type",
        "tax_amount",
    )
    search_fields = ("staff__surname", "staff__name")
    list_filter = ("staff__department", "contract_type")
    readonly_fields = ("total_salary", "tax_amount")
    actions = ["calculate_bonuses", "export_salary_report"]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": ("staff", "net_salary", "total_salary", "contract_type"),
                "classes": ("wide",),
            },
        ),
    )

    def staff_department(self, obj):
        return obj.staff.department.name if obj.staff.department else "N/A"

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department__name"

    def tax_amount(self, obj):
        tax_rate = 13
        tax = float(obj.net_salary) * (tax_rate / 100)
        return f"{tax:.2f} тг."

    tax_amount.short_description = "Сумма налога"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff__department")

    def calculate_bonuses(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Рассчитаны бонусы для {count} сотрудников.")

    calculate_bonuses.short_description = "Рассчитать бонусы для выбранных сотрудников"

    def export_salary_report(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Экспортирован отчет по зарплате для {count} сотрудников.")

    export_salary_report.short_description = "Экспортировать отчет по зарплате"


@admin.register(PublicHoliday, site=admin_site)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "is_working_day", "days_until")
    list_filter = ("is_working_day", "date")
    search_fields = ("name",)
    ordering = ("-date",)
    actions = ["mark_as_working", "mark_as_non_working"]

    fieldsets = (
        (
            "Информация о празднике",
            {
                "fields": ("date", "name", "is_working_day"),
                "classes": ("wide",),
            },
        ),
    )

    def days_until(self, obj):
        today = timezone.now().date()
        days = (obj.date - today).days

        if days < 0:
            return "Прошел"
        elif days == 0:
            return format_html('<span style="color: green; font-weight: bold;">Сегодня!</span>')
        elif days <= 7:
            return format_html('<span style="color: orange;">{} дн.</span>', days)
        else:
            return f"{days} дн."

    days_until.short_description = "Дней до праздника"

    def mark_as_working(self, request, queryset):
        updated = queryset.update(is_working_day=True)
        self.message_user(request, f"{updated} праздников отмечены как рабочие дни.")

    mark_as_working.short_description = "Отметить как рабочие дни"

    def mark_as_non_working(self, request, queryset):
        updated = queryset.update(is_working_day=False)
        self.message_user(request, f"{updated} праздников отмечены как нерабочие дни.")

    mark_as_non_working.short_description = "Отметить как нерабочие дни"


@admin.register(AbsentReason, site=admin_site)
class AbsentReasonAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "reason",
        "start_date",
        "end_date",
        "duration_days",
        "approved",
        "has_document",
    )
    list_filter = ("reason", "approved", "start_date")
    search_fields = ("staff__surname", "staff__name", "reason")
    readonly_fields = ("duration_days",)
    actions = ["approve_selected", "reject_selected"]

    fieldsets = (
        (
            "Информация об отсутствии",
            {
                "fields": (
                    "staff",
                    "reason",
                    ("start_date", "end_date"),
                    "document",
                    "approved",
                ),
                "classes": ("wide",),
            },
        ),
    )

    def duration_days(self, obj):
        if obj.start_date and obj.end_date:
            days = (obj.end_date - obj.start_date).days + 1
            return days
        return "Н/Д"

    duration_days.short_description = "Продолжительность (дней)"

    def has_document(self, obj):
        return bool(obj.document)

    has_document.boolean = True
    has_document.short_description = "Документ"

    def document_preview(self, obj):
        if obj.document:
            file_url = obj.document.url
            file_name = os.path.basename(file_url)
            extension = file_name.split(".")[-1].lower()

            if extension in ["jpg", "jpeg", "png", "gif"]:
                return format_html(
                    '<img src="{}" style="max-width: 300px; max-height: 300px;" />',
                    file_url,
                )
            elif extension == "pdf":
                return format_html(
                    '<a href="{}" target="_blank" class="button">Просмотреть PDF</a>',
                    file_url,
                )
            else:
                return format_html(
                    '<a href="{}" target="_blank" class="button">Скачать файл</a>',
                    file_url,
                )
        return "Документ не прикреплен"

    document_preview.short_description = "Предпросмотр документа"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff")

    def approve_selected(self, request, queryset):
        updated = queryset.update(approved=True)
        self.message_user(request, f"{updated} причин отсутствия одобрено.")

    approve_selected.short_description = "Одобрить выбранные причины отсутствия"

    def reject_selected(self, request, queryset):
        updated = queryset.update(approved=False)
        self.message_user(request, f"{updated} причин отсутствия отклонено.")

    reject_selected.short_description = "Отклонить выбранные причины отсутствия"


@admin.register(RemoteWork, site=admin_site)
class RemoteWorkAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "permanent_remote",
        "start_date",
        "end_date",
        "duration_days",
        "get_remote_status",
    )
    list_filter = ("permanent_remote", "start_date", "end_date")
    search_fields = ("staff__surname", "staff__name")
    actions = ["extend_remote_work", "terminate_remote_work"]

    fieldsets = (
        (
            "Удаленная работа",
            {
                "fields": ("staff", "permanent_remote", ("start_date", "end_date")),
                "classes": ("wide",),
            },
        ),
    )

    def duration_days(self, obj):
        if obj.permanent_remote:
            return "Постоянно"

        if obj.start_date and obj.end_date:
            days = (obj.end_date - obj.start_date).days + 1
            return f"{days} дн."
        return "Н/Д"

    duration_days.short_description = "Продолжительность"

    def get_remote_status(self, obj):
        status = obj.get_remote_status()

        if "Постоянно" in status:
            return format_html('<span style="color: green;">{}</span>', status)
        elif "Активно" in status:
            return format_html('<span style="color: blue;">{}</span>', status)
        elif "Завершено" in status:
            return format_html('<span style="color: gray;">{}</span>', status)
        elif "Ожидает" in status:
            return format_html('<span style="color: orange;">{}</span>', status)

        return status

    get_remote_status.short_description = "Статус удаленной работы"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff")

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            form.add_error(None, e)

    def extend_remote_work(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Период удаленной работы продлен для {count} сотрудников.")

    extend_remote_work.short_description = "Продлить период удаленной работы"

    def terminate_remote_work(self, request, queryset):
        today = timezone.now().date()
        count = queryset.filter(end_date__gt=today).update(end_date=today)
        self.message_user(request, f"Удаленная работа завершена для {count} сотрудников.")

    terminate_remote_work.short_description = "Завершить удаленную работу"


@admin.register(PerformanceBonusRule, site=admin_site)
class PerformanceBonusRuleAdmin(admin.ModelAdmin):
    list_display = (
        "min_days",
        "max_days",
        "min_attendance_percent",
        "max_attendance_percent",
        "bonus_percentage",
        "rule_description",
    )
    list_filter = (
        "min_days",
        "max_days",
        "min_attendance_percent",
        "max_attendance_percent",
    )
    search_fields = ("bonus_percentage", "min_days", "max_days")
    ordering = ("min_days", "max_days", "min_attendance_percent")

    fieldsets = (
        (
            "Критерии бонуса",
            {
                "fields": (
                    ("min_days", "max_days"),
                    ("min_attendance_percent", "max_attendance_percent"),
                    "bonus_percentage",
                ),
                "classes": ("wide",),
            },
        ),
    )

    def rule_description(self, obj):
        return f"За {obj.min_days}-{obj.max_days} дней с посещаемостью {obj.min_attendance_percent}%-{obj.max_attendance_percent}% бонус {obj.bonus_percentage}%"

    rule_description.short_description = "Описание правила"


for model, admin_class in admin.site._registry.items():
    if model not in admin_site._registry:
        admin_site.register(model, type(admin_class))

admin.site = admin_site
