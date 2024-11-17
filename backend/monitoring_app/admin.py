import os
from collections import defaultdict

from django.conf import settings
from django.contrib import admin
from django.utils import timezone
from django.core.cache import cache
from django.utils.html import format_html
from django_admin_geomap import ModelAdmin
from django.db.models import F, Func, Q, Value
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db.models.functions import Power, Sqrt

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
    PasswordResetRequestLog,
)

# Настройка заголовков административной панели
admin.site.site_header = "Панель управления"
admin.site.index_title = "Администрирование сайта"
admin.site.site_title = "Администрирование"

# === Фильтры ===


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
        departments = ChildDepartment.objects.all().select_related("parent")
        hierarchy = self.build_hierarchy(departments)
        lookup_list = self.get_department_choices(hierarchy)
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
        queue = [department_id]
        descendants = set(queue)
        while queue:
            current = queue.pop(0)
            children = ChildDepartment.objects.filter(parent_id=current).values_list(
                "id", flat=True
            )
            queue.extend(children)
            descendants.update(children)
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


# === Модели авторизации ===


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "used", "is_valid")
    list_filter = (UsedFilter, "created_at")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = ("user", "token", "created_at", "used", "is_valid")
    ordering = ("-created_at",)

    def is_valid(self, obj):
        return obj.is_valid()

    is_valid.boolean = True
    is_valid.short_description = "Действительный токен"

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "token", "created_at", "used", "is_valid"),
            },
        ),
    )


@admin.register(PasswordResetRequestLog)
class PasswordResetRequestLogAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "requested_at", "next_possible_request")
    list_filter = ("requested_at",)
    search_fields = ("user__username", "user__email", "ip_address")
    readonly_fields = ("user", "ip_address", "requested_at", "next_possible_request")
    ordering = ("-requested_at",)

    def next_possible_request(self, obj):
        return obj.requested_at + timezone.timedelta(minutes=5)

    next_possible_request.short_description = "Следующий возможный запрос"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "ip_address",
                    "requested_at",
                    "next_possible_request",
                ),
            },
        ),
    )


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("key_name", "created_by", "created_at", "short_key", "is_active")
    list_filter = ("created_at", "created_by", "is_active")
    list_editable = ("is_active",)
    search_fields = ("key_name", "created_by__username")
    ordering = ("-created_at", "key_name")
    readonly_fields = ("key", "created_at", "created_by")

    fieldsets = (
        (
            None,
            {
                "fields": ("key_name", "key", "is_active"),
            },
        ),
        (
            "Дополнительная информация",
            {
                "fields": ("created_by", "created_at"),
            },
        ),
    )

    def short_key(self, obj):
        return f"{obj.key[:8]}..."

    short_key.short_description = "Ключ"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_banned", "phonenumber", "last_login_ip")
    list_filter = ("is_banned",)
    search_fields = ("user__username", "phonenumber", "last_login_ip")
    ordering = ("user__username",)
    list_editable = ("is_banned",)

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "phonenumber", "last_login_ip"),
            },
        ),
        (
            "Статус",
            {
                "fields": ("is_banned",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("user")
        return qs


# === Категории файлов ===


@admin.register(FileCategory)
class FileCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


# === Отделы ===


@admin.register(ParentDepartment)
class ParentDepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "date_of_creation")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("date_of_creation",)

    fieldsets = (
        (
            None,
            {
                "fields": ("id", "name", "date_of_creation"),
            },
        ),
    )


@admin.register(ChildDepartment)
class ChildDepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "date_of_creation")
    search_fields = ("name", "parent__name")
    ordering = ("name",)
    list_filter = ("parent",)
    readonly_fields = ("date_of_creation",)

    fieldsets = (
        (
            None,
            {
                "fields": ("id", "name", "parent", "date_of_creation"),
            },
        ),
    )


# === Должности ===


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "rate")
    search_fields = ("name",)
    ordering = ("-rate", "name")
    list_editable = ("rate",)

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "rate"),
            },
        ),
    )


# === Сотрудники ===


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


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "pin",
        "full_name",
        "department",
        "display_positions",
        "needs_training_status",
        "avatar_thumbnail",
    )
    list_filter = (DepartmentHierarchyFilter, "positions", "needs_training")
    search_fields = ("pin", "surname", "name", "department__name")
    filter_horizontal = ("positions",)
    actions = [
        "clear_avatars",
        "assign_position",
        "mark_needs_training_true",
    ]
    ordering = ("-pin", "-department", "surname", "name")
    inlines = [SalaryInline, AbsentReasonInline, RemoteWorkInline]
    readonly_fields = ("pin", "avatar_thumbnail")

    fieldsets = (
        (
            "Личная информация",
            {
                "fields": (("surname", "name"), "pin", "avatar", "avatar_thumbnail"),
            },
        ),
        (
            "Должность и отдел",
            {
                "fields": ("department", "positions"),
            },
        ),
        (
            "Машинное обучение",
            {
                "fields": ("needs_training",),
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
        return (
            "Нуждается в тренировке"
            if obj.needs_training
            else "Тренировка не требуется"
        )

    needs_training_status.short_description = "Статус тренировки ML"

    def display_positions(self, obj):
        return ", ".join(position.name for position in obj.positions.all())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("department").prefetch_related("positions")
        return qs

    display_positions.short_description = "Должности"

    def clear_avatars(self, request, queryset):
        queryset.update(avatar=None)

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


# === Маски Пользователей ===


@admin.register(StaffFaceMask)
class StaffFaceMaskAdmin(admin.ModelAdmin):
    from monitoring_app import utils

    list_display = (
        "staff",
        "staff_department",
        "created_at",
        "updated_at",
        "staff_avatar",
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

    def staff_avatar(self, obj):
        if obj.staff.avatar:
            return format_html(
                '<img src="{}" width="100" height="100" style="border-radius: 50%;" />',
                obj.staff.avatar.url,
            )
        return "No Avatar"

    staff_avatar.short_description = "Аватар сотрудника"

    def augmented_images(self, obj):
        cache_key = f"augmented_images_{obj.staff.pin}"
        images_html = cache.get(cache_key)

        if images_html is None:
            augmented_dir = str(settings.AUGMENT_ROOT).format(staff_pin=obj.staff.pin)
            if not os.path.exists(augmented_dir):
                return "No Augmented Images"

            pattern = f"{obj.staff.pin}_augmented_"
            images_html = ""
            with os.scandir(augmented_dir) as it:
                for entry in it:
                    if (
                        entry.is_file()
                        and entry.name.startswith(pattern)
                        and entry.name.endswith(".jpg")
                    ):
                        images_html += (
                            f'<img src="{os.path.join(settings.AUGMENT_URL, obj.staff.pin, entry.name)}" '
                            f'width="80" height="80" style="margin: 5px;" />'
                        )

            if not images_html:
                return "No Augmented Images"

            cache.set(cache_key, images_html, timeout=3600)

        return format_html(images_html)

    augmented_images.short_description = "Аугментированные фото"

    def staff_department(self, obj):
        return obj.staff.department

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "staff",
                    "staff_avatar",
                    "augmented_images",
                )
            },
        ),
        (
            "Временные метки",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
        (
            "Encoded Faces",
            {
                "fields": ("mask_encoding",),
            },
        ),
    )


# === Посещаемость сотрудников ===


@admin.register(StaffAttendance)
class StaffAttendanceAdmin(admin.ModelAdmin):
    from monitoring_app import utils

    list_display = (
        "staff",
        "staff_department",
        "date_at",
        "first_in",
        "last_out",
        "area_name_in",
        "area_name_out",
        "absence_reason",
    )
    list_filter = (
        utils.HierarchicalDepartmentFilter,
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

    readonly_fields = ("staff", "date_at", "first_in", "last_out")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "staff",
                    "date_at",
                    "first_in",
                    "last_out",
                    "absence_reason",
                ),
            },
        ),
    )

    def staff_department(self, obj):
        return obj.staff.department.name if obj.staff.department else "N/A"

    staff_department.short_description = "Отдел"
    staff_department.admin_order_field = "staff__department__name"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("staff__department").only(
            "staff__department__name",
            "staff__pin",
            "staff__surname",
            "staff__name",
            "date_at",
            "first_in",
            "last_out",
            "absence_reason",
            "area_name_in",
            "area_name_out",
        )

        return qs.exclude(
            Q(area_name_in__isnull=True)
            | Q(area_name_out__isnull=True)
            | Q(area_name_in="Unknown")
            | Q(area_name_out="Unknown")
        )

    def area_name_in(self, obj):
        return (
            obj.area_name_in
            if obj.area_name_in and obj.area_name_in != "Unknown"
            else "N/A"
        )

    def area_name_out(self, obj):
        return (
            obj.area_name_out
            if obj.area_name_out and obj.area_name_out != "Unknown"
            else "N/A"
        )

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        response["Cache-Control"] = "max-age=60, public"
        return response


# === Посещаемость занятий ===
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
    )
    date_hierarchy = "date_at"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_in",
                    "last_out",
                    "photo_preview",
                    "latitude",
                    "longitude",
                    "date_at",
                ),
                "description": "Основная информация о занятии",
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
                "description": "Информация о преподавателе и предмете",
            },
        ),
    )

    list_display = (
        "staff",
        "tutor",
        "formatted_first_in",
        "formatted_last_out",
        "date_at",
        "has_photo",
        "closest_location",
    )

    list_filter = (
        "date_at",
        "staff",
        "subject_name",
        ("first_in", admin.DateFieldListFilter),
        ("last_out", admin.DateFieldListFilter),
    )

    search_fields = (
        "staff__name",
        "subject_name",
        "tutor",
        "tutor_id",
    )

    ordering = ("-date_at", "-first_in")

    def formatted_first_in(self, obj):
        if obj.first_in:
            local_time = timezone.localtime(obj.first_in)
            return local_time.strftime("%H:%M:%S %d.%m.%Y")
        return "-"

    formatted_first_in.short_description = "Время начала (локальное)"

    def formatted_last_out(self, obj):
        if obj.last_out:
            local_time = timezone.localtime(obj.last_out)
            return local_time.strftime("%H:%M:%S %d.%m.%Y")
        return "Продолжается"

    formatted_last_out.short_description = "Время окончания (локальное)"

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

        radius = 200  # в метрах
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
            return format_html(
                "{}<br><small>{}</small>", location.name, location.address
            )
        else:
            return "N/A"

    closest_location.short_description = "Ближайшая локация"

    def photo_preview(self, obj):
        if obj.staff_image_path:
            return format_html(
                """
                <div style="display: flex; justify-content: center; align-items: center; height: 80px; width: 80px; overflow: hidden; border-radius: 50%;">
                    <img src="{}" style="
                        height: 100%;
                        width: 100%;
                        object-fit: cover;
                        display: block;
                    "/>
                </div>
                """,
                obj.image_url,
            )
        return format_html(
            """
            <div style="display: flex; justify-content: center; align-items: center; height: 80px; width: 80px; border-radius: 50%; background-color: #f0f0f0;">
                <span style="color: #999; font-style: italic; text-align: center;">Нет фото</span>
            </div>
            """
        )

    photo_preview.short_description = "Фото (превью)"


admin.site.register(LessonAttendance, LessonAttendanceAdmin)


# === Локации занятий ===
class ClassLocationAdmin(ModelAdmin):
    geomap_field_longitude = "longitude"
    geomap_field_latitude = "latitude"
    geomap_show_map_on_list = False
    geomap_item_zoom = "14"
    geomap_height = "450px"
    geomap_default_zoom = "16"
    geomap_autozoom = "15.9"

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": ("name", "address", "latitude", "longitude"),
                "description": "Информация о локации учебного заведения и координаты",
            },
        ),
        (
            "Системная информация",
            {
                "fields": ("created_at", "updated_at"),
                "description": "Внутренние поля системы",
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

    def formatted_latitude(self, obj):
        return f"{obj.latitude:.6f}"

    formatted_latitude.short_description = "Широта"

    def formatted_longitude(self, obj):
        return f"{obj.longitude:.6f}"

    formatted_longitude.short_description = "Долгота"


admin.site.register(ClassLocation, ClassLocationAdmin)

# === Зарплата ===


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ("staff", "net_salary", "total_salary", "contract_type")
    search_fields = ("staff__surname", "staff__name")
    list_filter = ("staff__department", "contract_type")
    readonly_fields = ("total_salary",)

    fieldsets = (
        (
            None,
            {
                "fields": ("staff", "net_salary", "total_salary", "contract_type"),
            },
        ),
    )


# === Праздничные дни ===


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "is_working_day")
    list_filter = ("is_working_day",)
    search_fields = ("name",)
    ordering = ("-date",)

    fieldsets = (
        (
            None,
            {
                "fields": ("date", "name", "is_working_day"),
            },
        ),
    )


# === Уважительные причины отсутствия ===


@admin.register(AbsentReason)
class AbsentReasonAdmin(admin.ModelAdmin):
    list_display = ("staff", "reason", "start_date", "end_date", "approved")
    list_filter = ("reason", "approved")
    search_fields = ("staff__surname", "staff__name")
    readonly_fields = ("approved",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "staff",
                    "reason",
                    ("start_date", "end_date"),
                    "document",
                    "approved",
                ),
            },
        ),
    )


# === Дистанционная работа ===


@admin.register(RemoteWork)
class RemoteWorkAdmin(admin.ModelAdmin):
    list_display = ("staff", "get_remote_status")
    list_filter = ("permanent_remote",)
    search_fields = ("staff__surname", "staff__name")

    fieldsets = (
        (
            None,
            {
                "fields": ("staff", "permanent_remote", ("start_date", "end_date")),
            },
        ),
    )

    def get_remote_status(self, obj):
        return obj.get_remote_status()

    get_remote_status.short_description = "Статус дистанционной работы"

    def save_model(self, request, obj, form, change):
        try:
            obj.full_clean()
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            form.add_error(None, e)
