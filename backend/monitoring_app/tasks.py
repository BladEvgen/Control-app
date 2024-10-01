from . import utils
from celery import shared_task

@shared_task
def get_all_attendance_task():
    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()
