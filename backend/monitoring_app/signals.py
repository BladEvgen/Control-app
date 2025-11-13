import re
import logging
from django.dispatch import receiver
from .models import LessonAttendance, Staff
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save

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


@receiver(post_save, sender=Staff)
def mark_staff_for_training(sender, instance: Staff, created, **kwargs):
    if not instance.avatar:
        return
    try:
        # debounce by checking a simple per-instance cache via model flag
        if not instance.needs_training:
            instance.needs_training = True
            instance.save(update_fields=["needs_training"])
        from monitoring_app.tasks import align_and_augment_staff, build_embeddings_for_staff
        try:
            align_and_augment_staff.apply_async(args=[instance.pin]),
            build_embeddings_for_staff.apply_async(args=[instance.pin])
        except Exception as e:
            logger.exception("Failed to enqueue training tasks for %s: %s", instance.pin, e)
    except Exception as e:
        logger.exception("Error in mark_staff_for_training for %s: %s", instance.pin, e)
