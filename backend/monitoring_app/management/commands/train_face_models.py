import logging

from monitoring_app.models import Staff
from django.core.management.base import BaseCommand
from monitoring_app.utils import train_face_recognition_model

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Тренировка модели по верификации лиц"

    def handle(self, *args, **kwargs):
        staff_members = (
            Staff.objects.filter(needs_training=True)
            .exclude(avatar__isnull=True)
            .exclude(avatar="")
        )

        if not staff_members.exists():
            self.stdout.write(self.style.WARNING("No staff members need training."))

        for staff in staff_members:
            self.stdout.write(
                f"Training model for {staff.name} {staff.surname} (PIN: {staff.pin})"
            )
            try:
                train_face_recognition_model(staff)
                staff.needs_training = False
                staff.save()
                logger.info(f"Successfully trained model for {staff.pin}")
                self.stdout.write(
                    self.style.SUCCESS(f"Model trained successfully for {staff.pin}")
                )
            except Exception as e:
                logger.error(f"Error training model for {staff.pin}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Error training model for {staff.pin}: {str(e)}")
                )
