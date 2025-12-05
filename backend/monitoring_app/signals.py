import logging
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import LessonAttendance, StaffAttendance, Staff, ChildDepartment
from .cache_conf import invalidate_cache, invalidate_cache_pattern

logger = logging.getLogger(__name__)


def sanitize_group_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)[:100]


@receiver(post_save, sender=LessonAttendance)
def send_new_photo(_sender, instance, created, **kwargs):
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
def invalidate_attendance_cache(_sender, instance, **kwargs):
    """Инвалидирует кэш при изменении посещаемости сотрудников."""
    if hasattr(instance, "date_at") and instance.date_at:
        date_str = instance.date_at.strftime("%Y-%m-%d")
        invalidate_cache_pattern(f"staff_attendance_stats_{date_str}*")
        if hasattr(instance, "staff") and instance.staff:
            invalidate_cache_pattern(f"staff_detail_{instance.staff.pin}*")
        invalidate_cache_pattern(f"map_location_{date_str}*")
        logger.info(f"Invalidated attendance cache for date: {date_str}")


@receiver([post_save, post_delete], sender=Staff)
def invalidate_staff_cache(_sender, instance, **kwargs):
    """Инвалидирует кэш при изменении данных сотрудника."""
    if hasattr(instance, "pin") and instance.pin:
        invalidate_cache(f"staff_{instance.pin}")
        invalidate_cache_pattern(f"staff_detail_{instance.pin}*")
        if hasattr(instance, "department") and instance.department:
            invalidate_cache(f"child_department_detail_{instance.department.id}")
        logger.info(f"Invalidated staff cache for PIN: {instance.pin}")


@receiver([post_save, post_delete], sender=ChildDepartment)
def invalidate_department_cache(_sender, instance, **kwargs):
    """Инвалидирует кэш при изменении департаментов."""
    dept_id = str(instance.id)
    invalidate_cache(f"department_summary_{dept_id}")
    invalidate_cache(f"child_department_detail_{dept_id}")
    invalidate_cache_pattern(f"staff_detail_{dept_id}*")
    invalidate_cache("parent_department_ids")
    logger.info(f"Invalidated department cache for ID: {dept_id}")
