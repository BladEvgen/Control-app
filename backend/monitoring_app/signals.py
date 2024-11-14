import logging
from monitoring_app import models
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

@receiver(post_save, sender=models.LessonAttendance)
def send_new_photo(sender, instance, created, **kwargs):
    if created:
        logger.info(f"send_new_photo called for LessonAttendance ID: {instance.id}")
        channel_layer = get_channel_layer()
        date_str = instance.date_at.isoformat()
        group_name = f'photos_{date_str}'
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'new_photo',
                'staff_pin': instance.staff.pin,
                'attendance_id': instance.id,
            }
        )
