import logging
from celery import shared_task
from django.utils import timezone
from monitoring_app import utils, models

@shared_task
def get_all_attendance_task():
    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()


logger = logging.getLogger(__name__)


@shared_task
def process_lesson_attendance_batch(attendance_data):
    """
    Задача для обработки создания посещаемости занятий.
    """
    success_records = []
    error_records = []

    for record in attendance_data:
        try:
            staff_pin = record.get('staff_pin')
            subject_name = record.get('subject_name')
            tutor_id = record.get('tutor_id')
            tutor = record.get('tutor')
            first_in = record.get('first_in')
            latitude = record.get('latitude')
            longitude = record.get('longitude')
            date_at = record.get('date_at')

            if not all([staff_pin, subject_name, tutor_id, tutor, first_in, latitude, longitude]):
                raise ValueError("Отсутствуют обязательные поля.")

            staff = models.Staff.objects.get(pin=staff_pin)

            lesson_attendance = models.LessonAttendance.objects.create(
                staff=staff,
                subject_name=subject_name,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=first_in,
                latitude=latitude,
                longitude=longitude,
                date_at=date_at or timezone.now().date(),
            )

            success_records.append(
                {"id": lesson_attendance.id}
            )

        except Exception as e:
            error_records.append({"staff_pin": staff_pin, "error": str(e)})

    return {"success_records": success_records, "error_records": error_records}
