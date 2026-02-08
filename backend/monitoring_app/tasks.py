import datetime
import logging
import os

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from monitoring_app import models, utils

logger = logging.getLogger(__name__)


@shared_task
def get_all_attendance_task():
    import asyncio

    from monitoring_app.attendance_fetcher import AsyncAttendanceFetcher

    async def main():
        fetcher = AsyncAttendanceFetcher()
        summary = await fetcher.get_all_attendance()
        return summary

    summary = asyncio.run(main())
    logger.info(
        "get_all_attendance_task summary: total_pins=%s, successful=%s, failed=%s, created=%s, updated=%s",
        summary.get("total_pins"),
        summary.get("successful_requests"),
        summary.get("failed_requests"),
        summary.get("created_records"),
        summary.get("updated_records"),
    )
    return summary


@shared_task
def update_lesson_attendance_last_out():
    """Updates the last_out field for lesson attendance records that have been open for more than 3 hours.

    This task handles the automatic closure of lesson attendance records by setting the last_out time
    based on the following rules:
    1. Finds all lessons without last_out time that started more than 3 hours ago
    2. For each lesson:
        - If the target time (first_in + 3 hours) is on the same day, sets last_out to that time
        - If the target time crosses midnight, sets last_out to 23:59:59.999999 of the start day

    The processing is done in batches to optimize memory usage and database performance.

    Note:
        - Uses Django's timezone-aware datetime handling
        - Processes records in batches of 1000
        - Performs bulk updates to minimize database calls

    Returns:
        None

    Raises:
        Exception: If any error occurs during processing. All exceptions are logged and re-raised.

    Example:
        >>> update_lesson_attendance_last_out.delay()  # When called as Celery task
        >>> update_lesson_attendance_last_out()  # When called directly

    Performance Considerations:
        - Uses batch processing with configurable BATCH_SIZE (default: 1000)
        - Implements chunked iteration (chunk_size=100) for memory efficiency
        - Uses bulk_update for optimal database performance

    Logging:
        - INFO: Processing progress and successful updates
        - ERROR: Any exceptions during execution
        - INFO: No records found message when applicable
    """
    try:
        now = timezone.now()
        three_hours_ago = now - datetime.timedelta(hours=3)

        lessons_to_update = models.LessonAttendance.objects.filter(
            last_out__isnull=True, first_in__lte=three_hours_ago
        )

        if not lessons_to_update.exists():
            logger.info("No LessonAttendance records found for updating `last_out`.")
            return

        BATCH_SIZE = 1000
        total_updated = 0

        total_records = lessons_to_update.count()

        for offset in range(0, total_records, BATCH_SIZE):
            batch = lessons_to_update[offset : offset + BATCH_SIZE]

            updates = []

            for lesson in batch.iterator(chunk_size=100):
                first_in = lesson.first_in

                if not timezone.is_aware(first_in):
                    first_in = timezone.make_aware(
                        first_in, timezone.get_current_timezone()
                    )

                end_of_day = timezone.make_aware(
                    datetime.datetime.combine(
                        first_in.date(), datetime.time(23, 59, 59, 999999)
                    ),
                    first_in.tzinfo,
                )

                target_time = first_in + datetime.timedelta(hours=3)

                if target_time.date() > first_in.date():
                    last_out = end_of_day
                else:
                    last_out = target_time

                lesson.last_out = last_out
                updates.append(lesson)

            if updates:
                models.LessonAttendance.objects.bulk_update(
                    updates, ["last_out"], batch_size=100
                )
                total_updated += len(updates)

            if total_records > BATCH_SIZE:
                logger.info(
                    f"Processed {min(offset + BATCH_SIZE, total_records)}/{total_records} records"
                )

        logger.info(f"Successfully updated `last_out` for {total_updated} records.")

    except Exception as e:
        logger.error(
            f"Error executing `update_lesson_attendance_last_out`: {e}", exc_info=True
        )
        raise


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


@shared_task(
    name="monitoring_app.tasks.augment_user_images",
    bind=True,
    queue="control_app_queue",
)
def augment_user_images(_self):
    if not getattr(settings, "ENABLE_AUGMENT", False):
        logger.info("augment_user_images: disabled by settings")
        return "disabled"
    from monitoring_app.augment import run_dali_augmentation_for_all_staff

    return run_dali_augmentation_for_all_staff()


@shared_task(name="monitoring_app.tasks.warmup_class_location_buffers")
def warmup_class_location_buffers():
    """
    Прогревает кэш приёмных радиусов R_loc по локациям (Redis). Celery Beat раз в 30 мин.
    При первом запуске: manage.py warmup_class_location_buffers
    """
    from django.core.cache import caches
    from monitoring_app.lesson_locations_conf import (
        ACCEPTANCE_R_CLUSTER,
        ACCEPTANCE_R_SAME_POINT,
        ACCEPTANCE_R_STANDALONE,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
        CLUSTER_THRESHOLD_M,
        SAME_POINT_THRESHOLD_M,
    )

    locations = list(
        models.ClassLocation.objects.filter(
            latitude__isnull=False, longitude__isnull=False
        )
    )
    radii = utils.compute_class_location_acceptance_radii(
        locations,
        r_same_point=ACCEPTANCE_R_SAME_POINT,
        r_cluster=ACCEPTANCE_R_CLUSTER,
        r_standalone=ACCEPTANCE_R_STANDALONE,
        same_point_threshold=SAME_POINT_THRESHOLD_M,
        cluster_threshold=CLUSTER_THRESHOLD_M,
    )
    caches["default"].set(
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
        radii,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
    )
    logger.info(
        "warmup_class_location_buffers: записано %s приёмных радиусов в кэш",
        len(radii),
    )
    return {"count": len(radii)}


@shared_task(name="monitoring_app.tasks.warmup_cache_task")
def warmup_cache_task(force: bool = False, keys=None):
    """
    Celery задача для прогрева кэша (холодный и горячий кэш).

    Args:
        force (bool): Принудительно обновить кэш (горячий кэш).
        keys (list, optional): Список ключей для предзагрузки. Если None, загружаются все.

    Returns:
        dict: Результаты прогрева кэша.
    """
    from typing import List, Optional

    from monitoring_app.cache_conf import warmup_cache
    from monitoring_app.management.commands.warmup_cache import Command

    command = Command()
    command.handle(force=force, keys=keys)

    keys_list: Optional[List[str]] = keys if keys else None
    results = warmup_cache(keys=keys_list, force=force)

    logger.info(
        f"Cache warmup task completed. Success: {sum(1 for r in results.values() if r.get('status') == 'success')}/{len(results)}"
    )
    return results
