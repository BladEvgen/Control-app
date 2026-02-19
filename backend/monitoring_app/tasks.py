import datetime
import logging
import os
from pathlib import Path

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


@shared_task(name="monitoring_app.tasks.update_lesson_attendance_last_out")
def update_lesson_attendance_last_out():
    """Автоматически проставляет last_out для занятий без отметки об окончании.

    Студенты не ставят отметку «занятие закончилось», поэтому last_out выставляется
    автоматически: first_in + 3 часа, но НЕ ПОЗЖЕ конца дня занятия (date_at).

    Правила:
    1. Берём занятия без last_out, у которых first_in был более 3 часов назад
    2. last_out = min(first_in + 3ч, 23:59:59.999999 дня date_at)
    3. Гарантия: last_out никогда не выходит за пределы date_at (защита от 22:00→01:00)

    Используется date_at (дата занятия), а не first_in.date(), чтобы избежать
    косяков с часовыми поясами и корректно считать выгрузки по дням.
    """
    log_prefix = "[update_lesson_attendance_last_out]"
    try:
        now = timezone.now()
        three_hours_ago = now - datetime.timedelta(hours=3)

        lessons_to_update = models.LessonAttendance.objects.filter(
            last_out__isnull=True, first_in__lte=three_hours_ago
        )

        if not lessons_to_update.exists():
            logger.info("%s no records to update", log_prefix)
            return

        BATCH_SIZE = 1000
        total_updated = 0
        total_records = lessons_to_update.count()
        current_tz = timezone.get_current_timezone()

        for offset in range(0, total_records, BATCH_SIZE):
            batch = lessons_to_update[offset : offset + BATCH_SIZE]
            updates = []

            for lesson in batch.iterator(chunk_size=100):
                first_in = lesson.first_in
                if not timezone.is_aware(first_in):
                    first_in = timezone.make_aware(first_in, current_tz)

                lesson_date = lesson.date_at
                end_of_lesson_day = timezone.make_aware(
                    datetime.datetime.combine(
                        lesson_date, datetime.time(23, 59, 59, 999999)
                    ),
                    current_tz,
                )

                target_time = first_in + datetime.timedelta(hours=3)
                last_out = (
                    end_of_lesson_day
                    if target_time > end_of_lesson_day
                    else target_time
                )

                lesson.last_out = last_out
                updates.append(lesson)

            if updates:
                models.LessonAttendance.objects.bulk_update(
                    updates, ["last_out"], batch_size=100
                )
                total_updated += len(updates)

            if total_records > BATCH_SIZE:
                logger.info(
                    "%s progress %s/%s",
                    log_prefix,
                    min(offset + BATCH_SIZE, total_records),
                    total_records,
                )

        logger.info(
            "%s done updated=%s total=%s",
            log_prefix,
            total_updated,
            total_records,
        )

    except Exception as e:
        logger.exception("%s EXCEPTION error=%s", log_prefix, e)
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
    log_prefix = "[lesson_attendance_task]"
    success_records = []
    error_records = []

    records_count = len(attendance_data) if attendance_data else 0
    image_size = len(image_content) if image_content else 0
    logger.info(
        "%s start records=%s image_size_bytes=%s",
        log_prefix,
        records_count,
        image_size,
    )
    if not attendance_data:
        logger.warning("%s empty attendance_data list, nothing to process", log_prefix)
        return {"success_records": [], "error_records": []}

    for idx, record in enumerate(attendance_data):
        staff_pin = record.get("staff_pin")
        tutor_id = record.get("tutor_id")
        try:
            tutor = record.get("tutor")
            first_in = record.get("first_in")
            latitude = record.get("latitude")
            longitude = record.get("longitude")
            subject_name = record.get("subject_name") or ""

            timestamp = int(timezone.now().timestamp())
            image_name = f"{staff_pin}_{timestamp}.jpg"

            staff = models.Staff.objects.get(pin=staff_pin)

            date_path = timezone.now().strftime("%Y-%m-%d")
            base_path = (
                f"{settings.MEDIA_ROOT}/control_image/{staff_pin}/{date_path}"
                if settings.DEBUG
                else f"{settings.ATTENDANCE_ROOT}/{staff_pin}/{date_path}"
            )

            os.makedirs(base_path, exist_ok=True)
            file_path = os.path.join(base_path, image_name)

            try:
                with open(file_path, "wb") as destination:
                    destination.write(image_content)
            except OSError as e:
                logger.error(
                    "%s image_save_failed staff_pin=%s path=%s errno=%s error=%s",
                    log_prefix,
                    staff_pin,
                    file_path,
                    getattr(e, "errno", None),
                    str(e),
                )
                error_records.append(
                    {"staff_pin": staff_pin, "error": f"Image save failed: {e}"}
                )
                continue

            lesson_attendance = models.LessonAttendance.objects.create(
                staff=staff,
                subject_name=subject_name,
                tutor_id=tutor_id,
                tutor=tutor,
                first_in=first_in,
                latitude=latitude,
                longitude=longitude,
                date_at=timezone.now().date(),
                staff_image_path=file_path,
            )
            success_records.append({"id": lesson_attendance.id})
            logger.debug(
                "%s created lesson_id=%s staff_pin=%s tutor_id=%s",
                log_prefix,
                lesson_attendance.id,
                staff_pin,
                tutor_id,
            )

        except models.Staff.DoesNotExist:
            logger.warning(
                "%s staff_not_found staff_pin=%s tutor_id=%s record_index=%s (add Staff with this pin in control or fix journal payload)",
                log_prefix,
                staff_pin,
                tutor_id,
                idx,
            )
            error_records.append(
                {
                    "staff_pin": staff_pin,
                    "error": "Сотрудник с PIN не найден в БД (Staff.DoesNotExist)",
                }
            )
        except Exception as e:
            logger.exception(
                "%s record_exception staff_pin=%s tutor_id=%s record_index=%s error=%s",
                log_prefix,
                staff_pin,
                tutor_id,
                idx,
                str(e),
            )
            error_records.append({"staff_pin": staff_pin, "error": str(e)})

    logger.info(
        "%s done created=%s failed=%s failed_pins=%s",
        log_prefix,
        len(success_records),
        len(error_records),
        [r.get("staff_pin") for r in error_records],
    )
    if error_records:
        logger.warning(
            "%s error_details %s",
            log_prefix,
            error_records,
        )

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


@shared_task(name="monitoring_app.tasks.clean_old_attendance_photos")
def clean_old_attendance_photos(days_old=31):
    """
    Удаляет фотографии посещаемости (lesson_attendance) старше заданного числа дней.

    Сканирует ATTENDANCE_ROOT (директория из settings, либо env ATTENDANCE_ROOT),
    удаляет файлы с mtime старше days_old дней. Пустые директории удаляются после.

    Args:
        days_old: удалять файлы старше этого количества дней (по умолчанию 31).

    Returns:
        dict: {"deleted_files": int, "deleted_dirs": int, "root": str, "error": str | None}
    """
    log_prefix = "[lesson_attendance_cleanup]"
    root = getattr(settings, "ATTENDANCE_ROOT", None)
    if not root:
        logger.warning("%s ATTENDANCE_ROOT not configured, skip", log_prefix)
        return {
            "deleted_files": 0,
            "deleted_dirs": 0,
            "root": "",
            "error": "ATTENDANCE_ROOT not set",
        }

    root = Path(root).resolve()
    if not root.is_dir():
        logger.warning("%s root is not a directory: %s", log_prefix, root)
        return {
            "deleted_files": 0,
            "deleted_dirs": 0,
            "root": str(root),
            "error": "root is not a directory",
        }

    cutoff = timezone.now() - datetime.timedelta(days=days_old)
    cutoff_ts = cutoff.timestamp()

    try:
        to_delete = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff_ts:
                    to_delete.append(path)
            except OSError as e:
                logger.debug("%s skip stat %s: %s", log_prefix, path, e)

        deleted_files = 0
        for path in to_delete:
            try:
                path.unlink(missing_ok=True)
                deleted_files += 1
            except OSError as e:
                logger.warning("%s unlink failed %s: %s", log_prefix, path, e)

        deleted_dirs = 0
        for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
            if dirpath == str(root):
                continue
            try:
                d = Path(dirpath)
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
                    deleted_dirs += 1
            except OSError as e:
                logger.debug("%s skip rmdir %s: %s", log_prefix, dirpath, e)

        logger.info(
            "%s done root=%s days_old=%s deleted_files=%s deleted_dirs=%s (collected=%s)",
            log_prefix,
            root,
            days_old,
            deleted_files,
            deleted_dirs,
            len(to_delete),
        )
        return {
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs,
            "root": str(root),
            "error": None,
        }
    except Exception as e:
        logger.exception("%s EXCEPTION root=%s error=%s", log_prefix, root, e)
        return {
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs,
            "root": str(root),
            "error": str(e),
        }


def _class_location_row_to_obj(row):
    """Минимальный объект с .id, .latitude, .longitude, .acceptance_radius_m для compute_class_location_acceptance_radii."""
    return type(
        "Loc",
        (),
        {
            "id": row["id"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "acceptance_radius_m": row.get("acceptance_radius_m"),
        },
    )()


@shared_task(name="monitoring_app.tasks.warmup_class_location_buffers")
def warmup_class_location_buffers():
    """
    Прогревает кэш локаций в фоне: список (API GET) + приёмные радиусы R_loc.
    Celery Beat раз в 30 мин — первый юзер не создаёт кэш, он уже прогрет.
    Один запрос к БД для списка, радиусы считаются из тех же данных.
    """
    from django.core.cache import caches
    from monitoring_app.lesson_locations_conf import (
        ACCEPTANCE_R_CLUSTER,
        ACCEPTANCE_R_SAME_POINT,
        ACCEPTANCE_R_STANDALONE,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
        CLASS_LOCATION_LIST_CACHE_KEY,
        CLASS_LOCATION_LIST_CACHE_TTL,
        CLUSTER_THRESHOLD_M,
        SAME_POINT_THRESHOLD_M,
    )

    cache = caches["default"]
    list_data = list(
        models.ClassLocation.objects.order_by("id").values(
            "id",
            "name",
            "address",
            "latitude",
            "longitude",
            "acceptance_radius_m",
        )
    )
    cache.set(
        CLASS_LOCATION_LIST_CACHE_KEY,
        list_data,
        CLASS_LOCATION_LIST_CACHE_TTL,
    )
    locs_with_coords = [
        _class_location_row_to_obj(row)
        for row in list_data
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]
    radii = (
        utils.compute_class_location_acceptance_radii(
            locs_with_coords,
            r_same_point=ACCEPTANCE_R_SAME_POINT,
            r_cluster=ACCEPTANCE_R_CLUSTER,
            r_standalone=ACCEPTANCE_R_STANDALONE,
            same_point_threshold=SAME_POINT_THRESHOLD_M,
            cluster_threshold=CLUSTER_THRESHOLD_M,
        )
        if locs_with_coords
        else {}
    )
    cache.set(
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_KEY,
        radii,
        CLASS_LOCATION_ACCEPTANCE_RADII_CACHE_TTL,
    )
    logger.info(
        "warmup_class_location_buffers: список=%s, радиусов=%s",
        len(list_data),
        len(radii),
    )
    return {"list_count": len(list_data), "radii_count": len(radii)}


@shared_task(name="monitoring_app.tasks.invalidate_class_location_patterns")
def invalidate_class_location_patterns():
    """
    Асинхронная инвалидация ключей по паттернам (Redis KEYS может быть медленной).
    Вызывается из invalidate_class_location_cache_impl после синхронной инвалидации.
    """
    from monitoring_app.cache_conf import invalidate_cache_pattern

    n1 = invalidate_cache_pattern("class_location_neighbor_colors_*")
    n2 = invalidate_cache_pattern("attendance_stats_*")
    logger.info(
        "invalidate_class_location_patterns: neighbor_colors=%s attendance_stats=%s",
        n1,
        n2,
    )
    return {"class_location_neighbor_colors": n1, "attendance_stats": n2}


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
