import datetime
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union, cast

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from monitoring_app import models, utils
from monitoring_app.photo_ws_broadcast import (
    broadcast_lesson_attendance_photo_meta_updates,
)

logger = logging.getLogger(__name__)
DEPARTMENT_CONFIRMATION_EPOCH_CACHE_KEY = "department_confirmation_epoch_hour"
DEPARTMENT_CONFIRMATION_EPOCH_TTL = 5 * 60 * 60
PAD_SCAN_EXCEPTION_TAG = "scan_exception"
PAD_SCAN_LOCK_KEY_PREFIX = "photo_pad_scan_lock"


def _get_lesson_attendance_pad_lock_ttl() -> int:
    return max(10, int(getattr(settings, "PHOTO_PAD_WS_SCAN_LOCK_TTL", 180)))


def lesson_attendance_pad_lock_key(attendance_id: int) -> str:
    return f"{PAD_SCAN_LOCK_KEY_PREFIX}:{int(attendance_id)}"


def acquire_lesson_attendance_pad_lock(
    attendance_id: int, *, ttl: Optional[int] = None
) -> bool:
    timeout = _get_lesson_attendance_pad_lock_ttl() if ttl is None else max(10, ttl)
    return bool(
        cache.add(
            lesson_attendance_pad_lock_key(attendance_id),
            timezone.now().isoformat(),
            timeout=timeout,
        )
    )


def release_lesson_attendance_pad_lock(attendance_id: int) -> None:
    cache.delete(lesson_attendance_pad_lock_key(attendance_id))


def build_pad_scan_exception_update_kwargs(
    *, pad_model_version: str, exception_tag: str = PAD_SCAN_EXCEPTION_TAG
) -> dict[str, Any]:
    return {
        "photo_trust_confirmed": None,
        "photo_spoof_status": models.LessonAttendance.PHOTO_SPOOF_STATUS_ERROR,
        "photo_spoof_score": None,
        "photo_spoof_tags": [exception_tag],
        "photo_spoof_checked_at": timezone.now(),
        "photo_spoof_model_version": pad_model_version,
    }


def _lesson_attendance_pad_candidate_queryset(
    *,
    only_today: bool,
    backlog_only: bool = False,
):
    """Build the PAD candidate queryset for hourly or backlog scans.

    Args:
        only_today: Whether to keep only rows for the local current date.
        backlog_only: Whether to keep only rows older than the local current date.

    Returns:
        QuerySet of LessonAttendance rows still needing PAD work.
    """
    from monitoring_app.photo_pad import MANUAL_NONE

    q_checked_null = cast(Q, Q(photo_spoof_checked_at__isnull=True))
    q_pending = cast(
        Q,
        Q(photo_spoof_status=models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING),
    )
    q_error = cast(
        Q,
        Q(photo_spoof_status=models.LessonAttendance.PHOTO_SPOOF_STATUS_ERROR),
    )
    q_needs_scan = cast(Q, cast(Q, q_checked_null | q_pending) | q_error)
    q_has_path = cast(Q, Q(staff_image_path__isnull=False))
    q_non_empty = cast(Q, ~Q(staff_image_path=""))
    q_manual_none = cast(Q, Q(photo_manual_verdict=MANUAL_NONE))
    qs = models.LessonAttendance.objects.filter(
        cast(
            Q, cast(Q, cast(Q, q_has_path & q_non_empty) & q_manual_none) & q_needs_scan
        )
    )
    today = timezone.localdate()
    if only_today:
        return (
            qs.filter(date_at=today)
            .only("id", "date_at", "staff_image_path")
            .order_by("id")
        )
    if backlog_only:
        return (
            qs.filter(date_at__lt=today)
            .only("id", "date_at", "staff_image_path")
            .order_by("date_at", "id")
        )
    return qs.only("id", "date_at", "staff_image_path").order_by("date_at", "id")


def _run_lesson_attendance_pad_scan(
    *,
    records: list[models.LessonAttendance],
    device: str,
    batch_size: int,
    log_prefix: str,
    mode: str,
    pad_model_version: str,
) -> dict[str, Union[int, float, str]]:
    """Run PAD on the provided rows and persist results.

    Args:
        records: Ordered LessonAttendance rows to scan.
        device: PAD device hint.
        batch_size: Chunk size for progress logging.
        log_prefix: Prefix for log lines.
        mode: Human-readable scan mode for logs.

    Returns:
        Scan stats with counts and average latency.
    """
    from monitoring_app.photo_pad import MANUAL_NONE, check_photo, normalize_device

    resolved_device = normalize_device(device)
    total = len(records)
    oldest_date = records[0].date_at.isoformat() if records else "—"
    updated_records_by_date: dict[datetime.date, list[int]] = {}
    checked_count = 0
    status_counts: dict[str, int] = {
        "clean": 0,
        "review": 0,
        "suspicious": 0,
        "error": 0,
    }
    elapsed_sum_ms = 0.0

    logger.info(
        "%s start mode=%s total=%s batch_size=%s device=%s oldest_date=%s",
        log_prefix,
        mode,
        total,
        batch_size,
        resolved_device,
        oldest_date,
    )

    for start in range(0, total, batch_size):
        batch = records[start : start + batch_size]
        for record in batch:
            image_path = record.staff_image_path
            if not image_path:
                logger.warning("%s skip_empty_path pk=%s", log_prefix, record.pk)
                updated_rows = models.LessonAttendance.objects.filter(
                    pk=record.pk,
                    photo_manual_verdict=MANUAL_NONE,
                ).update(
                    **build_pad_scan_exception_update_kwargs(
                        pad_model_version=pad_model_version,
                    )
                )
                if updated_rows:
                    updated_records_by_date.setdefault(record.date_at, []).append(
                        record.id
                    )
                status_counts["error"] += 1
                checked_count += 1
                continue
            if not acquire_lesson_attendance_pad_lock(record.id):
                logger.info("%s skip_locked mode=%s pk=%s", log_prefix, mode, record.pk)
                continue
            try:
                try:
                    result = check_photo(image_path=image_path, device=resolved_device)
                except Exception as exc:
                    logger.exception(
                        "%s scan_exception mode=%s pk=%s path=%s error=%s",
                        log_prefix,
                        mode,
                        record.pk,
                        image_path,
                        exc,
                    )
                    update_kwargs = build_pad_scan_exception_update_kwargs(
                        pad_model_version=pad_model_version,
                    )
                    status_key = models.LessonAttendance.PHOTO_SPOOF_STATUS_ERROR
                else:
                    elapsed_sum_ms += result.elapsed_ms
                    update_kwargs = result.to_update_kwargs()
                    status_key = result.status

                checked_count += 1
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
                updated_rows = models.LessonAttendance.objects.filter(
                    pk=record.pk,
                    photo_manual_verdict=MANUAL_NONE,
                ).update(**update_kwargs)
                if updated_rows:
                    updated_records_by_date.setdefault(record.date_at, []).append(
                        record.id
                    )
                else:
                    logger.warning(
                        "%s pad_update_no_rows mode=%s pk=%s path=%s",
                        log_prefix,
                        mode,
                        record.pk,
                        image_path,
                    )
            except Exception as exc:
                logger.exception(
                    "%s record_exception mode=%s pk=%s path=%s error=%s",
                    log_prefix,
                    mode,
                    record.pk,
                    image_path,
                    exc,
                )
            finally:
                release_lesson_attendance_pad_lock(record.id)

        if total > batch_size:
            logger.info(
                "%s progress mode=%s %s/%s checked=%s suspicious=%s review=%s error=%s",
                log_prefix,
                mode,
                min(start + batch_size, total),
                total,
                checked_count,
                status_counts["suspicious"],
                status_counts["review"],
                status_counts["error"],
            )

    avg_ms = (elapsed_sum_ms / checked_count) if checked_count else 0.0
    broadcast_lesson_attendance_photo_meta_updates(
        updated_records_by_date,
        log_prefix=log_prefix,
    )
    logger.info(
        "%s done mode=%s checked=%s clean=%s review=%s suspicious=%s error=%s avg_ms=%.2f",
        log_prefix,
        mode,
        checked_count,
        status_counts["clean"],
        status_counts["review"],
        status_counts["suspicious"],
        status_counts["error"],
        avg_ms,
    )
    return {
        "checked": checked_count,
        "clean": status_counts["clean"],
        "review": status_counts["review"],
        "suspicious": status_counts["suspicious"],
        "error": status_counts["error"],
        "mode": mode,
        "oldest_date": oldest_date,
        "avg_ms": round(avg_ms, 2),
    }


def lesson_attendance_pad_rescan_eligible(
    record: models.LessonAttendance,
    *,
    force_manual: bool,
    auto_eligible_only: bool,
    pad_model_version: str,
) -> tuple[bool, Optional[str]]:
    """Decide whether a ``LessonAttendance`` row should be scanned inside Celery rescan.

    The admin action ``Пересканировать выбранные фото (auto)`` does not use this to
    drop manual or «fresh» rows: it calls :func:`prepare_lesson_attendance_admin_pad_full_rescan`
    first so only the selected ids are cleared and queued.

    Args:
        record: Row with ``staff_image_path``, manual verdict, and spoof metadata
            (``photo_spoof_*``) populated.
        force_manual: When ``True``, allow rescan even when a manual photo verdict is set.
        auto_eligible_only: When ``True``, skip rows that already have a current-model
            PAD result and are not pending, error, or never checked (hourly-style semantics).
        pad_model_version: Active :data:`monitoring_app.photo_pad.PAD_MODEL_VERSION` string.

    Returns:
        ``(True, None)`` if the row should be rescanned, else ``(False, reason)`` where
        ``reason`` is ``"no_photo"``, ``"manual"``, or ``"auto_ineligible"``.
    """
    from monitoring_app.photo_pad import MANUAL_NONE

    if not record.staff_image_path:
        return False, "no_photo"
    if not force_manual and record.photo_manual_verdict != MANUAL_NONE:
        return False, "manual"
    if auto_eligible_only and not force_manual:
        la = models.LessonAttendance
        pending = record.photo_spoof_status == la.PHOTO_SPOOF_STATUS_PENDING
        error_status = record.photo_spoof_status == la.PHOTO_SPOOF_STATUS_ERROR
        never_checked = record.photo_spoof_checked_at is None
        _ = pad_model_version
        if not (never_checked or pending or error_status):
            return False, "auto_ineligible"
    return True, None


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


@shared_task(name="monitoring_app.tasks.backup_db_task")
def backup_db_task(
    backup_format: str = "both",
    compress: bool = True,
    output_dir: str = "DB",
    keep_days: int = 30,
) -> dict[str, Any]:
    """Запускает management-команду ``backup_db`` из Celery/beat."""
    from django.core.management import call_command

    options = {
        "format": backup_format,
        "compress": compress,
        "output_dir": output_dir,
        "keep_days": keep_days,
    }
    call_command("backup_db", **options)
    logger.info("backup_db_task completed: %s", options)
    return options


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


def _normalize_lesson_datetime(
    value: datetime.datetime, current_tz: datetime.tzinfo
) -> datetime.datetime:
    if timezone.is_aware(value):
        return timezone.localtime(value, current_tz)
    return timezone.make_aware(value, current_tz)


def _get_lesson_auto_close_minutes(first_in: datetime.datetime) -> int:
    """Ступенчатое авто-закрытие занятия.

    Базовая идея:
    - дневные занятия живут до 2 часов;
    - вечерние (с 18:00) до 1.5 часов;
    - поздние (с 20:00) до 1 часа.

    Это заметно уменьшает "накрутку" от вечерних отметок, но остаётся
    достаточно мягким для реальных дежурств и поздних активностей.
    """
    local_first_in = timezone.localtime(first_in)
    evening_start_hour = max(
        0,
        int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_START_HOUR),
    )
    late_start_hour = max(
        evening_start_hour,
        int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_LATE_START_HOUR),
    )
    if local_first_in.hour >= late_start_hour:
        return max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES))
    if local_first_in.hour >= evening_start_hour:
        return max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES))
    return max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES))


def _calculate_lesson_auto_last_out(
    *,
    lesson_date: datetime.date,
    first_in: datetime.datetime,
    current_tz: datetime.tzinfo,
) -> tuple[datetime.datetime, int]:
    normalized_first_in = _normalize_lesson_datetime(first_in, current_tz)
    auto_close_minutes = _get_lesson_auto_close_minutes(normalized_first_in)
    end_of_lesson_day = timezone.make_aware(
        datetime.datetime.combine(lesson_date, datetime.time(23, 59, 59, 999999)),
        current_tz,
    )
    target_time = normalized_first_in + datetime.timedelta(minutes=auto_close_minutes)
    return (
        end_of_lesson_day if target_time > end_of_lesson_day else target_time,
        auto_close_minutes,
    )


@shared_task(name="monitoring_app.tasks.update_lesson_attendance_last_out")
def update_lesson_attendance_last_out():
    """Автоматически проставляет last_out для занятий без отметки об окончании.

    Используем ступенчатое правило по локальному времени начала занятия:
    - до 18:00: first_in + 120 мин;
    - c 18:00: first_in + 90 мин;
    - c 20:00: first_in + 60 мин.

    Любой рассчитанный last_out дополнительно ограничивается концом `date_at`,
    чтобы занятие не перетекало на следующий день.
    """
    log_prefix = "[update_lesson_attendance_last_out]"
    try:
        now = timezone.now()
        min_auto_close_minutes = min(
            max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES)),
            max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES)),
            max(1, int(settings.LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES)),
        )
        oldest_open_cutoff = now - datetime.timedelta(minutes=min_auto_close_minutes)

        lessons_to_update = models.LessonAttendance.objects.filter(
            last_out__isnull=True,
            first_in__lte=oldest_open_cutoff,
        ).only("id", "first_in", "last_out", "date_at")

        if not lessons_to_update.exists():
            logger.info("%s no records to update", log_prefix)
            return

        batch_size = 1000
        total_updated = 0
        total_records = lessons_to_update.count()
        current_tz = timezone.get_current_timezone()
        skipped_not_due = 0

        for offset in range(0, total_records, batch_size):
            batch = lessons_to_update[offset : offset + batch_size]
            updates = []

            for lesson in batch.iterator(chunk_size=100):
                last_out, auto_close_minutes = _calculate_lesson_auto_last_out(
                    lesson_date=lesson.date_at,
                    first_in=lesson.first_in,
                    current_tz=current_tz,
                )
                if last_out > now:
                    skipped_not_due += 1
                    continue

                lesson.first_in = _normalize_lesson_datetime(
                    lesson.first_in, current_tz
                )
                lesson.last_out = last_out
                updates.append(lesson)
                logger.debug(
                    "%s prepared lesson_id=%s auto_close_minutes=%s last_out=%s",
                    log_prefix,
                    lesson.id,
                    auto_close_minutes,
                    last_out.isoformat(),
                )

            if updates:
                models.LessonAttendance.objects.bulk_update(
                    updates, ["last_out"], batch_size=100
                )
                total_updated += len(updates)
                from monitoring_app.cache_conf import (
                    invalidate_lesson_attendance_derived_caches,
                )

                invalidate_lesson_attendance_derived_caches(
                    staff_ids=[lesson.staff_id for lesson in updates],
                    lesson_dates=[lesson.date_at for lesson in updates],
                )

            if total_records > batch_size:
                logger.info(
                    "%s progress %s/%s",
                    log_prefix,
                    min(offset + batch_size, total_records),
                    total_records,
                )

        logger.info(
            "%s done updated=%s total=%s skipped_not_due=%s",
            log_prefix,
            total_updated,
            total_records,
            skipped_not_due,
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


@shared_task(
    name="monitoring_app.tasks.scan_lesson_attendance_photos_hourly",
    queue="control_app_queue",
)
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

    Исторические записи, уже обработанные старой версией PAD, автоматически
    не пересканируются: hourly берёт только реально незавершённые строки
    (pending/error/never checked).
    """
    from monitoring_app.photo_pad import PAD_MODEL_VERSION

    log_prefix = "[lesson_photo_pad_hourly]"
    batch_size = max(
        1,
        int(batch_size or getattr(settings, "PHOTO_PAD_HOURLY_BATCH_SIZE", 100)),
    )
    max_records = max(
        1,
        int(max_records or getattr(settings, "PHOTO_PAD_HOURLY_MAX_RECORDS", 200)),
    )
    qs = _lesson_attendance_pad_candidate_queryset(
        only_today=only_today,
        backlog_only=False,
    )
    records = list(qs[:max_records]) if max_records else list(qs)
    return _run_lesson_attendance_pad_scan(
        records=records,
        device=device,
        batch_size=batch_size,
        log_prefix=log_prefix,
        mode=("today" if only_today else "all"),
        pad_model_version=PAD_MODEL_VERSION,
    )


@shared_task(
    name="monitoring_app.tasks.scan_lesson_attendance_photos_backlog",
    queue="control_app_queue",
)
def scan_lesson_attendance_photos_backlog(
    batch_size: int = 50,
    max_records: int = 100,
    device: str = "auto",
) -> dict[str, Union[int, float, str]]:
    """Scan the oldest historical PAD backlog outside the current local date.

    Args:
        batch_size: Chunk size for progress logging.
        max_records: Maximum number of backlog rows per run.
        device: PAD device hint.

    Returns:
        Scan stats for the bounded backlog pass.
    """
    from monitoring_app.photo_pad import PAD_MODEL_VERSION

    log_prefix = "[lesson_photo_pad_backlog]"
    hourly_batch = int(getattr(settings, "PHOTO_PAD_HOURLY_BATCH_SIZE", 100))
    hourly_max = int(getattr(settings, "PHOTO_PAD_HOURLY_MAX_RECORDS", 200))
    batch_size = max(1, int(batch_size or min(hourly_batch, 50)))
    max_records = max(1, int(max_records or max(50, min(hourly_max // 4, 100))))
    qs = _lesson_attendance_pad_candidate_queryset(
        only_today=False,
        backlog_only=True,
    )
    records = list(qs[:max_records]) if max_records else list(qs)
    return _run_lesson_attendance_pad_scan(
        records=records,
        device=device,
        batch_size=batch_size,
        log_prefix=log_prefix,
        mode="backlog",
        pad_model_version=PAD_MODEL_VERSION,
    )


def prepare_lesson_attendance_admin_pad_full_rescan(
    selected_ids: list[int],
) -> tuple[list[int], dict[str, int]]:
    """Clear PAD and manual photo fields, then return ids ready for Celery rescan.

    Used exclusively by the LessonAttendance admin action
    ``Пересканировать выбранные фото (auto)``. For every selected primary key that
    exists and has a non-empty ``staff_image_path``, resets spoof scores, tags,
    trust, and manual verdict columns to a pending clean slate, then notifies
    live photo meta subscribers so the UI matches the database.

    Args:
        selected_ids: Changelist selection order; duplicates keep the first
            occurrence only.

    Returns:
        ``(photo_ids, skipped_counts)`` where ``photo_ids`` preserves selection
        order among rows with photos, and ``skipped_counts`` has non-negative
        ``no_photo`` and ``not_found`` tallies.
    """
    la = models.LessonAttendance
    skipped = {"no_photo": 0, "not_found": 0}
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in selected_ids or []:
        try:
            parsed_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if parsed_id <= 0 or parsed_id in seen:
            continue
        seen.add(parsed_id)
        normalized_ids.append(parsed_id)

    if not normalized_ids:
        return [], skipped

    records = list(
        la.objects.filter(id__in=normalized_ids).only("id", "staff_image_path")
    )
    by_id = {row.id: row for row in records}
    photo_ids: list[int] = []
    for aid in normalized_ids:
        rec = by_id.get(aid)
        if rec is None:
            skipped["not_found"] += 1
            continue
        path = (rec.staff_image_path or "").strip()
        if not path:
            skipped["no_photo"] += 1
            continue
        photo_ids.append(aid)

    if not photo_ids:
        return [], skipped

    updated_by_date: dict[datetime.date, list[int]] = {}
    for pk, day in la.objects.filter(id__in=photo_ids).values_list("id", "date_at"):
        updated_by_date.setdefault(day, []).append(pk)

    la.objects.filter(id__in=photo_ids).update(
        photo_spoof_status=la.PHOTO_SPOOF_STATUS_PENDING,
        photo_spoof_score=None,
        photo_spoof_tags=[],
        photo_spoof_checked_at=None,
        photo_spoof_model_version="",
        photo_trust_confirmed=None,
        photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_NONE,
        photo_manual_comment="",
        photo_manual_by=None,
        photo_manual_at=None,
    )

    broadcast_lesson_attendance_photo_meta_updates(
        updated_by_date,
        log_prefix="[lesson_photo_pad_admin_prepare]",
    )

    return photo_ids, skipped


@shared_task(
    name="monitoring_app.tasks.rescan_lesson_attendance_photo_ids",
    queue="control_app_queue",
)
def rescan_lesson_attendance_photo_ids(
    attendance_ids: list[int] | tuple[int, ...],
    device: str = "auto",
    force_manual: bool = False,
    batch_size: int = 100,
    auto_eligible_only: bool = False,
) -> dict[str, Any]:
    """Фоновый перескан PAD для заданных LessonAttendance.id.

    Админ-экшен сначала вызывает
    :func:`prepare_lesson_attendance_admin_pad_full_rescan`, чтобы сбросить PAD и
    ручной вердикт только по выбранным строкам, затем ставит эту задачу в Celery.

    Args:
        attendance_ids: Явный список первичных ключей (только они участвуют; лишние id
            в БД не найдены — учитываются в ``skipped_not_found``).
        device: Подсказка устройства для Faster R-CNN / torch.
        force_manual: Если True — записывать результат PAD даже при ненулевом
            ручном вердикте (по умолчанию админ сбрасывает ручной вердикт заранее).
        batch_size: Размер чанка при обходе записей.
        auto_eligible_only: Если True — обрабатывать только реально незавершённые
            записи (never checked / ``pending`` / ``error``), без автоперескана
            старых уже обработанных строк. Админ обычно передаёт ``False`` после
            полного сброса.

    Returns:
        Счётчики обработанных, пропущенных и ошибок.
    """
    from monitoring_app.photo_pad import (
        MANUAL_NONE,
        PAD_MODEL_VERSION,
        check_photo,
        normalize_device,
    )

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
            "skipped_not_found": 0,
            "skipped_auto_ineligible": 0,
        }

    resolved_device = normalize_device(device)
    batch_size = max(1, int(batch_size or 100))
    logger.info(
        "%s start immediate check_photo run (not beat): ids=%s count=%s device=%s",
        log_prefix,
        normalized_ids,
        len(normalized_ids),
        resolved_device,
    )
    id_order = {attendance_id: idx for idx, attendance_id in enumerate(normalized_ids)}
    records = list(
        models.LessonAttendance.objects.filter(id__in=normalized_ids).only(
            "id",
            "date_at",
            "staff_image_path",
            "photo_manual_verdict",
            "photo_spoof_model_version",
            "photo_spoof_status",
            "photo_spoof_checked_at",
        )
    )
    records.sort(key=lambda item: id_order.get(item.id, 10**9))
    skipped_not_found = max(0, len(normalized_ids) - len(records))

    stats: dict[str, Any] = {
        "requested": len(normalized_ids),
        "checked": 0,
        "clean": 0,
        "review": 0,
        "suspicious": 0,
        "error": 0,
        "skipped_manual": 0,
        "skipped_no_photo": 0,
        "skipped_not_found": skipped_not_found,
        "skipped_auto_ineligible": 0,
        "device": resolved_device,
        "auto_eligible_only": bool(auto_eligible_only),
    }
    updated_records_by_date: dict[datetime.date, list[int]] = {}

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        for record in batch:
            eligible, skip_reason = lesson_attendance_pad_rescan_eligible(
                record,
                force_manual=force_manual,
                auto_eligible_only=auto_eligible_only,
                pad_model_version=PAD_MODEL_VERSION,
            )
            if not eligible:
                if skip_reason == "no_photo":
                    stats["skipped_no_photo"] += 1
                elif skip_reason == "manual":
                    stats["skipped_manual"] += 1
                elif skip_reason == "auto_ineligible":
                    stats["skipped_auto_ineligible"] += 1
                continue
            if not acquire_lesson_attendance_pad_lock(record.id):
                logger.info("%s skip_locked lesson_id=%s", log_prefix, record.id)
                continue
            image_path = record.staff_image_path
            try:
                if not image_path:
                    stats["skipped_no_photo"] += 1
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
                    update_kwargs = build_pad_scan_exception_update_kwargs(
                        pad_model_version=PAD_MODEL_VERSION,
                    )
                    status_key = models.LessonAttendance.PHOTO_SPOOF_STATUS_ERROR
                else:
                    update_kwargs = result.to_update_kwargs()
                    status_key = result.status

                try:
                    update_qs = models.LessonAttendance.objects.filter(pk=record.pk)
                    if not force_manual:
                        update_qs = update_qs.filter(photo_manual_verdict=MANUAL_NONE)
                    updated_rows = update_qs.update(**update_kwargs)
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
                    logger.warning(
                        "%s pad_update_no_rows lesson_id=%s force_manual=%s path=%s",
                        log_prefix,
                        record.id,
                        force_manual,
                        image_path,
                    )
                    continue
                stats["checked"] += 1
                stats[status_key] = int(stats.get(status_key, 0)) + 1
                updated_records_by_date.setdefault(record.date_at, []).append(record.id)
            finally:
                release_lesson_attendance_pad_lock(record.id)

    broadcast_lesson_attendance_photo_meta_updates(
        updated_records_by_date,
        log_prefix=log_prefix,
    )

    logger.info(
        "%s done requested=%s checked=%s clean=%s review=%s suspicious=%s error=%s "
        "skipped_manual=%s skipped_no_photo=%s skipped_not_found=%s "
        "skipped_auto_ineligible=%s auto_eligible_only=%s device=%s",
        log_prefix,
        stats["requested"],
        stats["checked"],
        stats["clean"],
        stats["review"],
        stats["suspicious"],
        stats["error"],
        stats["skipped_manual"],
        stats["skipped_no_photo"],
        stats["skipped_not_found"],
        stats["skipped_auto_ineligible"],
        stats["auto_eligible_only"],
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

    default_cache = caches["default"]
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
    default_cache.set(
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
    default_cache.set(
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
    from monitoring_app.cache_conf import warmup_cache
    from monitoring_app.management.commands.warmup_cache import Command

    command = Command()
    command.handle(force=force, keys=keys)

    keys_list: Optional[list[str]] = list(keys) if keys else None
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
