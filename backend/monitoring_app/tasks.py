import datetime
import logging
import os
from pathlib import Path
from typing import Any, Union, cast

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from monitoring_app import models, utils

logger = logging.getLogger(__name__)
DEPARTMENT_CONFIRMATION_EPOCH_CACHE_KEY = "department_confirmation_epoch_hour"
DEPARTMENT_CONFIRMATION_EPOCH_TTL = 5 * 60 * 60


@shared_task
def get_all_attendance_task(days=None):
    """
    Выгрузка посещаемости из API СКУД и сохранение в StaffAttendance.

    days: за сколько дней назад брать рабочий день (по умолчанию settings.DAYS, обычно 1).
    Пример: days=1 → вчера по локальной дате, date_at=сегодня; days=2 → позавчера, date_at=вчера.
    Для дозаполнения пропущенных дней вызывать с days=2, 3, ... (по одному запуску на день).
    """
    import asyncio

    from monitoring_app.attendance_fetcher import AsyncAttendanceFetcher

    async def main():
        fetcher = AsyncAttendanceFetcher()
        summary = await fetcher.get_all_attendance(days=days)
        return summary

    summary = asyncio.run(main())
    logger.info(
        "get_all_attendance_task(days=%s) summary: source_date=%s save_date=%s total_pins=%s, successful=%s, failed=%s, created=%s, updated=%s",
        days,
        summary.get("source_date"),
        summary.get("save_date"),
        summary.get("total_pins"),
        summary.get("successful_requests"),
        summary.get("failed_requests"),
        summary.get("created_records"),
        summary.get("updated_records"),
    )
    if summary.get("created_records", 0) or summary.get("updated_records", 0):
        try:
            from django.core.management import call_command

            call_command(
                "warmup_cache",
                keys=["today_attendance_stats", "map_locations_today"],
                force=True,
            )
            logger.info(
                "get_all_attendance_task: refreshed today_attendance_stats and map_locations_today"
            )
        except Exception as e:
            logger.warning("get_all_attendance_task: warmup_cache failed: %s", e)
    return summary


@shared_task(name="monitoring_app.tasks.sync_staff_from_api_task")
def sync_staff_from_api_task(dry_run: bool = False):
    """
    Удаляет из БД сотрудников (Staff), которых в API СКУД уже нет. Новых не добавляет.

    Args:
        dry_run: Если True — только показать, кого удалили бы, без изменений в БД.

    Returns:
        dict: Результат синхронизации:
            - "deleted" (int): количество удалённых записей;
            - "errors" (list): список строк с ошибками при проверке по API.
    """
    from monitoring_app.staff_sync import sync_staff_from_external

    result = sync_staff_from_external(dry_run=dry_run)
    logger.info(
        "sync_staff_from_api_task: deleted=%s errors=%s",
        result.get("deleted", 0),
        len(result.get("errors", [])),
    )
    return result


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
        ).only("id", "first_in", "last_out", "date_at")

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
def process_lesson_attendance_batch(attendance_data, _image_name, image_content):
    """
    Асинхронная задача для создания записей посещаемости с сохранением фотографий сотрудников.

    Функция обрабатывает список посещаемости и создает соответствующие записи в базе данных.
    Если фотография предоставлена, она сохраняется в файловой системе. Добавлены расширенные
    логирования для отслеживания ошибок и предупреждений.

    Args:
        attendance_data (list): Данные посещаемости (staff_pin, tutor_id, tutor,
            first_in, latitude, longitude, опционально subject_name).
        _image_name: Не используется; имя файла генерируется внутри (staff_pin + timestamp).
        image_content (bytes | None): Содержимое фото; при None записи создаются без фото.

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

            staff = models.Staff.objects.get(pin=staff_pin)

            file_path = None
            if image_content:
                base_dir, file_path = utils.get_lesson_attendance_photo_path(staff_pin)
                os.makedirs(base_dir, exist_ok=True)
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


@shared_task(name="monitoring_app.tasks.scan_lesson_attendance_photos_hourly")
def scan_lesson_attendance_photos_hourly(
    batch_size: int = 100,
    max_records: int = 200,
    device: str = "auto",
    only_today: bool = True,
):
    """Почасовой инкрементальный антифрод-скан фотографий LessonAttendance.

    Сканируются только записи с фотографией, требующие проверки, и без ручного
    override (photo_manual_verdict='none'). Результат автоматической проверки
    не перезаписывает ручные решения администратора.

    При only_today=True задача берёт только текущую локальную дату (date_at=today),
    и ограничивает объём одним запуском (max_records), чтобы остаток шёл в
    следующий час без перегруза.
    """
    from monitoring_app.photo_pad import (
        MANUAL_NONE,
        PAD_MODEL_VERSION,
        check_photo,
        normalize_device,
    )

    log_prefix = "[lesson_photo_pad_hourly]"
    batch_size = max(
        1,
        int(batch_size or getattr(settings, "PHOTO_PAD_HOURLY_BATCH_SIZE", 100)),
    )
    max_records = max(
        1,
        int(max_records or getattr(settings, "PHOTO_PAD_HOURLY_MAX_RECORDS", 200)),
    )
    resolved_device = normalize_device(device)
    target_date = timezone.localdate() if only_today else None

    q_checked_null = cast(Q, Q(photo_spoof_checked_at__isnull=True))
    q_version_old = cast(Q, ~Q(photo_spoof_model_version=PAD_MODEL_VERSION))
    q_pending = cast(
        Q,
        Q(photo_spoof_status=models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING),
    )
    inner_q = cast(Q, cast(Q, q_checked_null | q_version_old) | q_pending)
    q_has_path = cast(Q, Q(staff_image_path__isnull=False))
    q_non_empty = cast(Q, ~Q(staff_image_path=""))
    q_manual_none = cast(Q, Q(photo_manual_verdict=MANUAL_NONE))
    candidates_q = cast(
        Q,
        cast(Q, cast(Q, q_has_path & q_non_empty) & q_manual_none) & inner_q,
    )
    qs = models.LessonAttendance.objects.filter(candidates_q)
    if target_date is not None:
        qs = qs.filter(date_at=target_date)
    qs = qs.only("id", "staff_image_path").order_by("id")
    if max_records:
        records = list(qs[:max_records])
    else:
        records = list(qs)

    stats: dict[str, Union[int, float]] = {
        "checked": 0,
        "clean": 0,
        "review": 0,
        "suspicious": 0,
        "error": 0,
    }
    elapsed_sum_ms = 0.0
    total = len(records)

    logger.info(
        "%s start total=%s batch_size=%s max_records=%s device=%s date=%s",
        log_prefix,
        total,
        batch_size,
        max_records,
        resolved_device,
        target_date.isoformat() if target_date is not None else "all",
    )

    for start in range(0, total, batch_size):
        batch = records[start : start + batch_size]
        for record in batch:
            image_path = record.staff_image_path
            if not image_path:
                logger.warning(
                    "%s skip_empty_path pk=%s",
                    log_prefix,
                    record.pk,
                )
                stats["error"] += 1
                stats["checked"] += 1
                continue
            try:
                result = check_photo(image_path=image_path, device=resolved_device)
            except Exception as exc:
                logger.exception(
                    "%s scan_exception pk=%s path=%s error=%s",
                    log_prefix,
                    record.pk,
                    image_path,
                    exc,
                )
                stats["error"] += 1
                stats["checked"] += 1
                continue

            elapsed_sum_ms += result.elapsed_ms
            stats["checked"] += 1
            stats[result.status] = stats.get(result.status, 0) + 1
            models.LessonAttendance.objects.filter(pk=record.pk).update(
                **result.to_update_kwargs()
            )

        if total > batch_size:
            logger.info(
                "%s progress=%s/%s checked=%s suspicious=%s review=%s error=%s",
                log_prefix,
                min(start + batch_size, total),
                total,
                stats["checked"],
                stats["suspicious"],
                stats["review"],
                stats["error"],
            )

    avg_ms = (elapsed_sum_ms / stats["checked"]) if stats["checked"] else 0.0
    logger.info(
        "%s done checked=%s clean=%s review=%s suspicious=%s error=%s avg_ms=%.2f",
        log_prefix,
        stats["checked"],
        stats["clean"],
        stats["review"],
        stats["suspicious"],
        stats["error"],
        avg_ms,
    )
    stats["avg_ms"] = round(avg_ms, 2)
    return stats


@shared_task(name="monitoring_app.tasks.rescan_lesson_attendance_photo_ids")
def rescan_lesson_attendance_photo_ids(
    attendance_ids: list[int] | tuple[int, ...],
    device: str = "auto",
    force_manual: bool = False,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Фоновый перескан PAD для заданных LessonAttendance.id.

    Используется админ-экшеном, чтобы не блокировать HTTP-запрос и избежать 500/timeout
    при массовом перескане.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from django.core.cache import cache
    from monitoring_app.photo_pad import MANUAL_NONE, check_photo, normalize_device

    log_prefix = "[lesson_photo_pad_admin_ids]"
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in attendance_ids or []:
        try:
            parsed_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if parsed_id <= 0 or parsed_id in seen:
            continue
        seen.add(parsed_id)
        normalized_ids.append(parsed_id)

    if not normalized_ids:
        return {
            "requested": 0,
            "checked": 0,
            "clean": 0,
            "review": 0,
            "suspicious": 0,
            "error": 0,
            "skipped_manual": 0,
            "skipped_no_photo": 0,
        }

    resolved_device = normalize_device(device)
    batch_size = max(1, int(batch_size or 100))
    id_order = {attendance_id: idx for idx, attendance_id in enumerate(normalized_ids)}
    records = list(
        models.LessonAttendance.objects.filter(id__in=normalized_ids).only(
            "id",
            "date_at",
            "staff_image_path",
            "photo_manual_verdict",
        )
    )
    records.sort(key=lambda item: id_order.get(item.id, 10**9))

    stats: dict[str, Any] = {
        "requested": len(normalized_ids),
        "checked": 0,
        "clean": 0,
        "review": 0,
        "suspicious": 0,
        "error": 0,
        "skipped_manual": 0,
        "skipped_no_photo": 0,
        "device": resolved_device,
    }
    updated_records_by_date: dict[str, list[int]] = {}
    updated_dates: set[datetime.date] = set()

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        for record in batch:
            image_path = record.staff_image_path
            if not image_path:
                stats["skipped_no_photo"] += 1
                continue
            if not force_manual and record.photo_manual_verdict != MANUAL_NONE:
                stats["skipped_manual"] += 1
                continue
            try:
                result = check_photo(image_path=image_path, device=resolved_device)
            except Exception as exc:
                logger.exception(
                    "%s scan_exception lesson_id=%s path=%s error=%s",
                    log_prefix,
                    record.id,
                    image_path,
                    exc,
                )
                stats["error"] += 1
                stats["checked"] += 1
                continue

            try:
                update_qs = models.LessonAttendance.objects.filter(pk=record.pk)
                if not force_manual:
                    update_qs = update_qs.filter(photo_manual_verdict=MANUAL_NONE)
                updated_rows = update_qs.update(**result.to_update_kwargs())
            except Exception as exc:
                logger.exception(
                    "%s db_update_exception lesson_id=%s path=%s error=%s",
                    log_prefix,
                    record.id,
                    image_path,
                    exc,
                )
                stats["error"] += 1
                stats["checked"] += 1
                continue

            if not updated_rows:
                continue
            stats["checked"] += 1
            stats[result.status] = int(stats.get(result.status, 0)) + 1
            updated_dates.add(record.date_at)
            date_key = record.date_at.isoformat()
            updated_records_by_date.setdefault(date_key, []).append(record.id)

    for lesson_date in updated_dates:
        cache.delete(f"photos_for_{lesson_date}")

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        version_ts = timezone.now().isoformat()
        for iso_date, raw_ids in updated_records_by_date.items():
            unique_ids = list(dict.fromkeys(raw_ids))
            group_name = f"photos_{iso_date}"
            for chunk_start in range(0, len(unique_ids), 200):
                chunk = unique_ids[chunk_start : chunk_start + 200]
                payload = {
                    "type": "new_photo",
                    "attendance_ids": chunk,
                    "op": "updated",
                    "stateCode": "UPDATED_META",
                    "versionTs": version_ts,
                }
                if len(chunk) == 1:
                    payload["attendance_id"] = chunk[0]
                try:
                    async_to_sync(channel_layer.group_send)(group_name, payload)
                except Exception as exc:
                    logger.warning(
                        "%s ws_broadcast_failed date=%s ids=%s error=%s",
                        log_prefix,
                        iso_date,
                        chunk[:10],
                        exc,
                    )

    logger.info(
        "%s done requested=%s checked=%s clean=%s review=%s suspicious=%s error=%s skipped_manual=%s skipped_no_photo=%s device=%s",
        log_prefix,
        stats["requested"],
        stats["checked"],
        stats["clean"],
        stats["review"],
        stats["suspicious"],
        stats["error"],
        stats["skipped_manual"],
        stats["skipped_no_photo"],
        resolved_device,
    )
    return stats


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


@shared_task(name="monitoring_app.tasks.rotate_department_confirmation_cache_epoch")
def rotate_department_confirmation_cache_epoch():
    """
    Почасовая ротация кэша подтверждений посещаемости:
    1) ставит epoch-ключ текущего часа;
    2) очищает старые ключи department_confirmation_*.
    """
    from monitoring_app.cache_conf import Cache, invalidate_cache_pattern

    epoch_hour = timezone.localtime().strftime("%Y%m%d%H")
    Cache.set(
        DEPARTMENT_CONFIRMATION_EPOCH_CACHE_KEY,
        epoch_hour,
        DEPARTMENT_CONFIRMATION_EPOCH_TTL,
    )
    deleted_count = invalidate_cache_pattern("department_confirmation_*")
    logger.info(
        "rotate_department_confirmation_cache_epoch: epoch=%s deleted=%s",
        epoch_hour,
        deleted_count,
    )
    return {"epoch": epoch_hour, "deleted_keys": deleted_count}
