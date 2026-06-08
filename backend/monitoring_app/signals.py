import logging
import re
from datetime import timedelta
from typing import Any, cast

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .cache_conf import (
    Cache,
    invalidate_cache,
    invalidate_cache_pattern,
    invalidate_lesson_attendance_derived_caches,
    invalidate_staff_detail_for_department,
    invalidate_staff_detail_for_pin,
)
from .lesson_locations_conf import (
    CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
    CLASS_LOCATION_LIST_CACHE_KEY,
    CLASS_LOCATION_LIST_CACHE_TTL,
    PUBLIC_HOLIDAY_LIST_CACHE_KEY,
    PUBLIC_HOLIDAY_LIST_CACHE_TTL,
)
from .models import (
    ChildDepartment,
    ClassLocation,
    LessonAttendance,
    PublicHoliday,
    Staff,
    StaffAttendance,
)

logger = logging.getLogger(__name__)
STATE_CREATED_NO_PHOTO = "CREATED_NO_PHOTO"
STATE_PHOTO_ATTACHED = "PHOTO_ATTACHED"
STATE_UPDATED_META = "UPDATED_META"
STATE_DELETED = "DELETED"
SUSPICIOUS_LOCATION_PATTERNS_EPOCH_CACHE_KEY = "suspicious_location_patterns_epoch"
SUSPICIOUS_LOCATION_PATTERNS_EPOCH_TTL = 365 * 24 * 60 * 60


def sanitize_group_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)[:100]


def _send_photo_event(instance, *, op, state_code):
    """Шлёт событие по LessonAttendance в группу по дате записи."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning(
            "Skipping photo event for attendance_id=%s op=%s state=%s: no channel layer",
            instance.id,
            op,
            state_code,
        )
        return
    group_name = sanitize_group_name(f"photos_{instance.date_at.isoformat()}")
    event_type = "attendance_deleted" if op == "deleted" else "new_photo"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": event_type,
                "attendance_id": instance.id,
                "attendance_ids": [instance.id],
                "op": op,
                "stateCode": state_code,
                "versionTs": timezone.now().isoformat(),
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to send photo event attendance_id=%s op=%s state=%s error=%s",
            instance.id,
            op,
            state_code,
            exc,
        )
        return
    logger.info(
        "Sent photo event to group %s for attendance_id %s op=%s state=%s",
        group_name,
        instance.id,
        op,
        state_code,
    )


def bump_suspicious_location_patterns_epoch() -> str:
    epoch_value = timezone.now().isoformat()
    Cache.set(
        SUSPICIOUS_LOCATION_PATTERNS_EPOCH_CACHE_KEY,
        epoch_value,
        SUSPICIOUS_LOCATION_PATTERNS_EPOCH_TTL,
    )
    return epoch_value


def _resolve_state_code(instance, *, created, update_fields):
    if created:
        return (
            STATE_PHOTO_ATTACHED
            if instance.staff_image_path
            else STATE_CREATED_NO_PHOTO
        )
    if update_fields and "staff_image_path" in update_fields:
        return STATE_PHOTO_ATTACHED if instance.staff_image_path else STATE_UPDATED_META
    return STATE_UPDATED_META


def _enqueue_immediate_photo_pad_scan(instance: LessonAttendance) -> None:
    if not instance.id or not instance.staff_image_path:
        return

    def _enqueue() -> None:
        from monitoring_app.tasks import rescan_lesson_attendance_photo_ids

        rescan_task = cast(Any, rescan_lesson_attendance_photo_ids)
        rescan_task.apply_async(
            kwargs={
                "attendance_ids": [int(instance.id)],
                "force_manual": False,
                "batch_size": 1,
                "auto_eligible_only": True,
            }
        )
        logger.info(
            "Queued immediate PAD scan for attendance_id=%s after photo attach",
            instance.id,
        )

    transaction.on_commit(_enqueue)


def _invalidate_lesson_attendance_cache(instance):
    invalidate_lesson_attendance_derived_caches(
        staff_ids=[instance.staff_id],
        lesson_dates=[instance.date_at],
    )
    bump_suspicious_location_patterns_epoch()


@receiver(post_save, sender=LessonAttendance)
def send_new_photo(sender, instance, created, **kwargs):
    _ = sender
    update_fields = kwargs.get("update_fields")
    state_code = _resolve_state_code(
        instance,
        created=created,
        update_fields=update_fields,
    )
    op = "created" if created else "updated"
    _invalidate_lesson_attendance_cache(instance)
    _send_photo_event(instance, op=op, state_code=state_code)
    if state_code == STATE_PHOTO_ATTACHED:
        _enqueue_immediate_photo_pad_scan(instance)


@receiver(post_delete, sender=LessonAttendance)
def send_deleted_photo(sender, instance, **kwargs):
    _ = sender
    _ = kwargs
    _invalidate_lesson_attendance_cache(instance)
    _send_photo_event(instance, op="deleted", state_code=STATE_DELETED)


@receiver([post_save, post_delete], sender=StaffAttendance)
def invalidate_attendance_cache(sender, instance, **kwargs):
    """Инвалидирует кэш при изменении посещаемости сотрудников (в т.ч. после fetcher)."""
    _ = sender
    _ = kwargs
    from .cache_conf import staff_detail_cache_version

    invalidate_cache_pattern("attendance_data_*")
    invalidate_cache_pattern("staffatt_count_*")
    version = staff_detail_cache_version()
    if hasattr(instance, "date_at") and instance.date_at:
        work_day = instance.date_at - timedelta(days=1)
        work_day_str = work_day.strftime("%Y-%m-%d")
        invalidate_cache_pattern(f"staff_attendance_stats_{version}_*")
        invalidate_cache_pattern(f"map_location_{version}_*")
        if hasattr(instance, "staff") and instance.staff and instance.staff.pin:
            invalidate_staff_detail_for_pin(instance.staff.pin)
        logger.info(f"Invalidated attendance cache for work_day: {work_day_str}")
    dept_id = (
        Staff.objects.filter(pk=instance.staff_id)
        .values_list("department_id", flat=True)
        .first()
    )
    if dept_id is not None:
        invalidate_cache_pattern(f"department_confirmation_{dept_id}_*")


@receiver(post_save, sender=Staff)
def invalidate_staff_cache_on_save(sender, instance, created, **kwargs):
    _ = sender
    _ = created
    _ = kwargs
    if hasattr(instance, "pin") and instance.pin:
        invalidate_cache_pattern("attendance_data_*")
        invalidate_cache(f"staff_{instance.pin}")
        invalidate_staff_detail_for_pin(instance.pin)
        if hasattr(instance, "department") and instance.department:
            invalidate_cache(f"child_department_detail_v2_{instance.department.id}")
        bump_suspicious_location_patterns_epoch()
        logger.info(f"Invalidated staff cache for PIN: {instance.pin}")


@receiver(post_delete, sender=Staff)
def invalidate_staff_cache_on_delete(sender, instance, **kwargs):
    _ = sender
    _ = kwargs
    if hasattr(instance, "pin") and instance.pin:
        invalidate_cache_pattern("attendance_data_*")
        invalidate_cache(f"staff_{instance.pin}")
        invalidate_staff_detail_for_pin(instance.pin)
        if hasattr(instance, "department") and instance.department:
            invalidate_cache(f"child_department_detail_v2_{instance.department.id}")
        invalidate_cache_pattern("staff_attendance_stats_*")
        bump_suspicious_location_patterns_epoch()
        logger.info(f"Invalidated staff cache for PIN: {instance.pin}")


@receiver([post_save, post_delete], sender=ChildDepartment)
def invalidate_department_cache(sender, instance, **kwargs):
    """Инвалидирует кэш при изменении департаментов."""
    sender_name = getattr(sender, "__name__", str(sender))
    dept_id = str(instance.id)
    invalidate_cache(f"department_summary_v2_{dept_id}")
    invalidate_cache(f"child_department_detail_v2_{dept_id}")
    invalidate_staff_detail_for_department(int(instance.id))
    invalidate_cache("parent_department_ids")
    invalidate_cache("root_departments_batch")
    invalidate_cache("department_hierarchy_lookups")
    invalidate_cache("hierarchical_dept_filter_lookups")
    invalidate_cache_pattern("department_descendants_*")
    invalidate_cache_pattern("dept_descendants_*")
    logger.info(
        "Invalidated department cache for sender=%s id=%s",
        sender_name,
        dept_id,
    )


def invalidate_class_location_cache_impl():
    """Инвалидирует кэш ClassLocation, сразу прогревает список и шлёт задачу прогрева радиусов. TTL списка 1 ч."""
    invalidate_cache_pattern("attendance_data_*")
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
    bump_suspicious_location_patterns_epoch()
    logger.info("Invalidated ClassLocation cache and warmed list + buffers task")


@receiver([post_save, post_delete], sender=ClassLocation)
def invalidate_class_location_cache(sender, instance, **kwargs):
    """Сигнал: инвалидирует кэш при изменении ClassLocation."""
    _ = sender
    _ = instance
    _ = kwargs
    invalidate_class_location_cache_impl()


def invalidate_public_holiday_cache_impl():
    """Инвалидирует кэш PublicHoliday (список API и ключи отчётов)."""
    invalidate_cache(PUBLIC_HOLIDAY_LIST_CACHE_KEY)
    invalidate_cache("public_holidays")
    invalidate_cache("public_holidays_for_excel")
    try:
        list_data = list(
            PublicHoliday.objects.order_by("date").values(
                "id", "date", "name", "is_working_day"
            )
        )
        Cache.set(
            PUBLIC_HOLIDAY_LIST_CACHE_KEY,
            list_data,
            PUBLIC_HOLIDAY_LIST_CACHE_TTL,
        )
    except Exception as e:
        logger.warning("PublicHoliday list cache warmup failed: %s", e)
    logger.info("Invalidated PublicHoliday cache and warmed list")


@receiver([post_save, post_delete], sender=PublicHoliday)
def invalidate_public_holiday_cache(sender, instance, **kwargs):
    """Сигнал: инвалидирует кэш при изменении PublicHoliday."""
    _ = sender
    _ = instance
    _ = kwargs
    invalidate_public_holiday_cache_impl()
