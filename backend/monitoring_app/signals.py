import logging
import re
from typing import Any, cast

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache_conf import invalidate_cache, invalidate_cache_pattern
from .lesson_locations_conf import (
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
    CLASS_LOCATION_LIST_CACHE_KEY,
    CLASS_LOCATION_LIST_CACHE_TTL,
)
from .models import (
    ChildDepartment,
    ClassLocation,
    LessonAttendance,
    Staff,
    StaffAttendance,
)

logger = logging.getLogger(__name__)


def sanitize_group_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)[:100]


@receiver(post_save, sender=LessonAttendance)
def send_new_photo(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = sanitize_group_name(f"photos_{instance.date_at.isoformat()}")
        async_to_sync(channel_layer.group_send)(
            group_name, {"type": "new_photo", "attendance_id": instance.id}
        )
        logger.info(
            f"Sent new_photo event to group {group_name} for attendance_id {instance.id}"
        )
        invalidate_cache_pattern(f"map_location_{instance.date_at}*")
        invalidate_cache_pattern(f"staff_attendance_stats_{instance.date_at}*")


@receiver([post_save, post_delete], sender=StaffAttendance)
def invalidate_attendance_cache(sender, instance, **kwargs):
    """Инвалидирует кэш при изменении посещаемости сотрудников."""
    invalidate_cache_pattern("staffatt_count_*")
    if hasattr(instance, "date_at") and instance.date_at:
        date_str = instance.date_at.strftime("%Y-%m-%d")
        invalidate_cache_pattern(f"staff_attendance_stats_{date_str}*")
        if hasattr(instance, "staff") and instance.staff:
            invalidate_cache_pattern(f"staff_detail_{instance.staff.pin}*")
        invalidate_cache_pattern(f"map_location_{date_str}*")
        logger.info(f"Invalidated attendance cache for date: {date_str}")


@receiver(post_save, sender=Staff)
def invalidate_staff_cache_on_save(sender, instance, created, **kwargs):
    _ = sender
    _ = created
    if hasattr(instance, "pin") and instance.pin:
        invalidate_cache(f"staff_{instance.pin}")
        invalidate_cache_pattern(f"staff_detail_{instance.pin}*")
        if hasattr(instance, "department") and instance.department:
            invalidate_cache(f"child_department_detail_{instance.department.id}")
        logger.info(f"Invalidated staff cache for PIN: {instance.pin}")


@receiver(post_delete, sender=Staff)
def invalidate_staff_cache_on_delete(sender, instance, **kwargs):
    if hasattr(instance, "pin") and instance.pin:
        invalidate_cache(f"staff_{instance.pin}")
        invalidate_cache_pattern(f"staff_detail_{instance.pin}*")
        if hasattr(instance, "department") and instance.department:
            invalidate_cache(f"child_department_detail_{instance.department.id}")
        invalidate_cache_pattern("staff_attendance_stats_*")
        logger.info(f"Invalidated staff cache for PIN: {instance.pin}")


@receiver([post_save, post_delete], sender=ChildDepartment)
def invalidate_department_cache(sender, instance, **kwargs):
    """Инвалидирует кэш при изменении департаментов."""
    dept_id = str(instance.id)
    invalidate_cache(f"department_summary_{dept_id}")
    invalidate_cache(f"child_department_detail_{dept_id}")
    invalidate_cache_pattern(f"staff_detail_{dept_id}*")
    invalidate_cache("parent_department_ids")
    invalidate_cache("root_departments_batch")
    invalidate_cache("department_hierarchy_lookups")
    invalidate_cache("hierarchical_dept_filter_lookups")
    invalidate_cache_pattern("department_descendants_*")
    invalidate_cache_pattern("dept_descendants_*")
    logger.info(f"Invalidated department cache for ID: {dept_id}")


def invalidate_class_location_cache_impl():
    """Инвалидирует кэш ClassLocation, сразу прогревает список и шлёт задачу прогрева радиусов. TTL списка 1 ч."""
    from monitoring_app.cache_conf import Cache

    invalidate_cache(CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY)
    invalidate_cache("lesson_admin_closest_locations")
    invalidate_cache(CLASS_LOCATION_LIST_CACHE_KEY)
    try:
        from monitoring_app.views import CLASS_LOCATION_CACHE

        CLASS_LOCATION_CACHE["expires_at"] = None
    except Exception:
        pass
    try:
        list_data = list(
            ClassLocation.objects.order_by("id").values(
                "id",
                "name",
                "address",
                "latitude",
                "longitude",
                "acceptance_radius_m",
            )
        )
        Cache.set(
            CLASS_LOCATION_LIST_CACHE_KEY,
            list_data,
            CLASS_LOCATION_LIST_CACHE_TTL,
        )
    except Exception as e:
        logger.warning("ClassLocation list cache warmup failed: %s", e)
    try:
        from celery import current_app

        send_task = cast(Any, getattr(current_app, "send_task"))
        send_task("monitoring_app.tasks.invalidate_class_location_patterns")
        send_task("monitoring_app.tasks.warmup_class_location_buffers")
    except Exception as e:
        logger.warning("ClassLocation cache tasks send_task failed: %s", e)
    logger.info("Invalidated ClassLocation cache and warmed list + buffers task")


@receiver([post_save, post_delete], sender=ClassLocation)
def invalidate_class_location_cache(sender, instance, **kwargs):
    """Сигнал: инвалидирует кэш при изменении ClassLocation."""
    invalidate_class_location_cache_impl()
