import re
import logging
from django.dispatch import receiver
from .models import LessonAttendance
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
