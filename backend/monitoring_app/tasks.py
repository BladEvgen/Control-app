import os
import logging
import datetime

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from monitoring_app import models


@shared_task
def get_all_attendance_task():
    from monitoring_app import utils

    """
    Задача Celery для выполнения функции get_all_attendance.
    """
    utils.get_all_attendance()


logger = logging.getLogger(__name__)


@shared_task
def update_lesson_attendance_last_out():
    """
    Периодическая задача Celery для обновления поля last_out в LessonAttendance.

    Условия выполнения:
    - last_out не установлен (last_out is null).
    - Прошло более 3 часов с момента first_in.

    Процесс:
    1. Определяет все записи, которые соответствуют условиям.
    2. Для каждой записи рассчитывает значение last_out:
       - Устанавливает last_out как first_in + 3 часа.
       - Если first_in + 3 часа выходит за пределы текущего дня, устанавливает last_out
         на максимально допустимое время в пределах дня (23:59:59).
    3. Изменяет записи в БД.

    Логирует информацию, предупреждения и ошибки для отслеживания процесса.
    """
    try:
        three_hours_ago = timezone.now() - datetime.timedelta(hours=3)

        lessons = models.LessonAttendance.objects.filter(
            last_out__isnull=True, first_in__lte=three_hours_ago
        )

        if not lessons.exists():
            logger.warning("Нет записей для обновления Lesson Attendance last_out.")
            return

        updated_lessons = []
        for lesson in lessons:
            first_in = lesson.first_in
            end_of_day = first_in.replace(hour=23, minute=59, second=59, microsecond=0)

            lesson.last_out = min(first_in + datetime.timedelta(hours=3), end_of_day)
            updated_lessons.append(lesson)

        models.LessonAttendance.objects.bulk_update(updated_lessons, ["last_out"])

        logger.warning(
            f"Обновлено {len(updated_lessons)} записей: last_out установлен успешно."
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении update_lesson_attendance_last_out: {e}")


@shared_task
def process_lesson_attendance_batch(attendance_data, image_name, image_content):
    """
    Асинхронная задача для создания записей посещаемости с сохранением фотографий сотрудников.

    Функция обрабатывает список посещаемости и создает соответствующие записи в базе данных.
    Если фотография предоставлена, она сохраняется в файловой системе. Добавлены расширенные
    логирования для отслеживания ошибок и предупреждений.

    Args:
        attendance_data (list): Данные посещаемости, где каждый элемент содержит:
            - staff_pin (str): Уникальный PIN сотрудника.
            - tutor_id (int): Идентификатор преподавателя.
            - tutor (str): ФИО преподавателя.
            - first_in (str): Дата и время начала занятия в формате ISO 8601.
            - latitude (float): Географическая широта места занятия.
            - longitude (float): Географическая долгота места занятия.
        image_name (str): Название файла для сохранения фотографии.
        image_content (bytes): Содержимое изображения в формате байтов.

    Returns:
        dict: Результат обработки задачи с информацией об успешных и неудачных записях:
            - "success_records" (list): ID успешно созданных записей.
            - "error_records" (list): Ошибки с описанием проблемы.

    Raises:
        Exception: Логирует подробные ошибки при сохранении записи или изображения.
    """
    success_records = []
    error_records = []

    for record in attendance_data:
        try:
            staff_pin = record.get("staff_pin")
            tutor_id = record.get("tutor_id")
            tutor = record.get("tutor")
            first_in = record.get("first_in")
            latitude = record.get("latitude")
            longitude = record.get("longitude")

            timestamp = int(timezone.now().timestamp())
            image_name = f"{staff_pin}_{timestamp}.jpg"

            staff = models.Staff.objects.get(pin=staff_pin)
            logger.info(f"Найден сотрудник с PIN: {staff_pin}")

            date_path = timezone.now().strftime("%Y-%m-%d")
            base_path = (
                f"{settings.MEDIA_ROOT}/control_image/{staff_pin}/{date_path}"
                if settings.DEBUG
                else f"{settings.ATTENDANCE_ROOT}/{staff_pin}/{date_path}"
            )

            os.makedirs(base_path, exist_ok=True)
            logger.info(f"Создан путь для сохранения изображений: {base_path}")

            file_path = os.path.join(base_path, image_name)

            try:
                with open(file_path, "wb") as destination:
                    destination.write(image_content)
                logger.info(f"Фотография успешно сохранена: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении файла изображения: {str(e)}")
                raise

            lesson_attendance = models.LessonAttendance.objects.create(
                staff=staff,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=first_in,
                latitude=latitude,
                longitude=longitude,
                date_at=timezone.now().date(),
                staff_image_path=file_path,
            )
            logger.info(
                f"Запись посещаемости успешно создана с ID: {lesson_attendance.id}"
            )

            success_records.append({"id": lesson_attendance.id})

        except models.Staff.DoesNotExist:
            error_message = f"Сотрудник с PIN {staff_pin} не найден."
            logger.warning(error_message)
            error_records.append({"staff_pin": staff_pin, "error": error_message})
        except Exception as e:
            logger.error(f"Общая ошибка при обработке записи посещаемости: {str(e)}")
            error_records.append({"staff_pin": staff_pin, "error": str(e)})

    logger.info(f"Итоговые успешные записи: {success_records}")
    logger.warning(f"Итоговые ошибки записи: {error_records}")

    return {"success_records": success_records, "error_records": error_records}
