from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import LessonAttendance
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=LessonAttendance)
def send_new_photo(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = f"photos_{instance.date_at}"
        async_to_sync(channel_layer.group_send)(
            group_name, {"type": "new_photo", "attendance_id": instance.id}
        )
        logger.info(
            f"Sent new_photo event to group {group_name} for attendance_id {instance.id}"
        )
