import asyncio
import logging
from contextlib import AbstractContextManager
from datetime import datetime as dt
from datetime import time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
import backoff
from channels.db import database_sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from monitoring_app import models
from monitoring_app.cache_conf import invalidate_cache, invalidate_cache_pattern

logger = logging.getLogger("django")


class AtomicBlock(AbstractContextManager[None]):
    def __init__(self) -> None:
        self._context = transaction.atomic()

    def __enter__(self) -> None:
        self._context.__enter__()
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        return self._context.__exit__(exc_type, exc_value, traceback)


def atomic_block() -> AtomicBlock:
    return AtomicBlock()


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
    "sec-ch-ua-platform": '"Windows"',
}

SENSITIVE_QUERY_KEYS = {"access_token", "token", "api_key", "apikey"}
MAX_RESPONSE_BODY_PREVIEW_LEN = 300


def _sanitize_url(raw_url: str) -> str:
    try:
        parsed_url = urlsplit(raw_url)
        redacted_query = urlencode(
            [
                (
                    key,
                    "***" if key.lower() in SENSITIVE_QUERY_KEYS else value,
                )
                for key, value in parse_qsl(parsed_url.query, keep_blank_values=True)
            ],
            doseq=True,
        )
        return urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                redacted_query,
                parsed_url.fragment,
            )
        )
    except Exception:
        return raw_url


def _shorten_payload(payload: str, max_len: int = MAX_RESPONSE_BODY_PREVIEW_LEN) -> str:
    if not payload:
        return ""
    one_line_payload = " ".join(payload.split())
    if len(one_line_payload) <= max_len:
        return one_line_payload
    return f"{one_line_payload[:max_len]}..."


class AsyncAttendanceFetcher:
    def __init__(self, max_concurrent_requests: int = 6):
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests must be greater than 0")
        self.max_concurrent_requests = max_concurrent_requests
        self.session = None
        logger.info(
            "AsyncAttendanceFetcher initialized with max_concurrent_requests=%s",
            self.max_concurrent_requests,
        )

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        conn = aiohttp.TCPConnector(limit_per_host=20)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=conn)
        logger.info(
            "Created aiohttp session with timeout=30s and TCPConnector(limit_per_host=20)"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            logger.info("Closed aiohttp session")

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientConnectionError, asyncio.TimeoutError),
        max_tries=3,
    )
    async def fetch_attendance(
        self, pin: str, start_date: dt, end_date: dt
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Запрашивает у API СКУД события посещаемости по одному сотруднику за период.

        Args:
            pin: PIN сотрудника (personPin в API).
            start_date: Начало периода (timezone-aware datetime).
            end_date: Конец периода (timezone-aware datetime).

        Returns:
            Кортеж (data, error): data — список словарей событий; error — словарь
            с полями ошибки или None при успехе.

        Raises:
            RuntimeError: Если сессия aiohttp не инициализирована.
        """
        if self.session is None:
            raise RuntimeError("aiohttp session is not initialized")

        params = {
            "endDate": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "pageNo": "1",
            "pageSize": "1000",
            "personPin": pin,
            "startDate": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "access_token": settings.API_KEY,
        }
        request_url = (
            f"{settings.API_URL.rstrip('/')}/api/transaction/listAttTransaction"
        )
        logger.debug("Fetching attendance for PIN %s", pin)

        try:
            async with self.session.get(
                request_url,
                params=params,
                headers=BROWSER_HEADERS,
                ssl=True,
            ) as response:
                response_body = await response.text()
                sanitized_response_url = _sanitize_url(str(response.url))
                shortened_response_body = _shorten_payload(response_body)

                if response.status != 200:
                    error_data = {
                        "pin": pin,
                        "status": response.status,
                        "url": sanitized_response_url,
                        "error": "External API responded with non-200 status",
                        "response_body_preview": shortened_response_body,
                    }
                    logger.error(
                        "Attendance API error for PIN %s: status=%s, url=%s, response_body=%s",
                        pin,
                        response.status,
                        sanitized_response_url,
                        shortened_response_body,
                    )
                    return [], error_data

                try:
                    data = await response.json(content_type=None)
                except Exception as decode_error:
                    logger.error(
                        "Attendance API returned non-JSON payload for PIN %s: url=%s, error=%s, response_body=%s",
                        pin,
                        sanitized_response_url,
                        str(decode_error),
                        shortened_response_body,
                    )
                    return (
                        [],
                        {
                            "pin": pin,
                            "status": response.status,
                            "url": sanitized_response_url,
                            "error": f"Invalid JSON payload: {decode_error}",
                            "response_body_preview": shortened_response_body,
                        },
                    )

                if not isinstance(data, dict):
                    logger.error(
                        "Attendance API returned unexpected payload type for PIN %s: %s",
                        pin,
                        type(data).__name__,
                    )
                    return (
                        [],
                        {
                            "pin": pin,
                            "status": response.status,
                            "url": sanitized_response_url,
                            "error": "Unexpected payload format",
                        },
                    )

                raw_records = data.get("data", [])
                if not isinstance(raw_records, list):
                    logger.error(
                        "Attendance API returned invalid 'data' field for PIN %s: %s",
                        pin,
                        type(raw_records).__name__,
                    )
                    return (
                        [],
                        {
                            "pin": pin,
                            "status": response.status,
                            "url": sanitized_response_url,
                            "error": "Invalid payload: field 'data' must be a list",
                        },
                    )

                logger.debug(
                    "Fetched %d attendance records for PIN %s",
                    len(raw_records),
                    pin,
                )
                return raw_records, None
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            logger.warning(
                "Temporary network error while fetching attendance for PIN %s. Will retry if attempts remain.",
                pin,
                exc_info=True,
            )
            raise
        except aiohttp.ClientError as client_error:
            logger.error(
                "Client error while fetching attendance for PIN %s: %s",
                pin,
                str(client_error),
                exc_info=True,
            )
            return (
                [],
                {
                    "pin": pin,
                    "error": f"Client error: {client_error}",
                },
            )
        except Exception as unknown_error:
            logger.error(
                "Unexpected error while fetching attendance for PIN %s: %s",
                pin,
                str(unknown_error),
                exc_info=True,
            )
            return (
                [],
                {
                    "pin": pin,
                    "error": f"Unexpected error: {unknown_error}",
                },
            )

    async def get_all_attendance(self, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Получает данные о посещаемости всех сотрудников за выбранный день.
        Логика:
         - Текущая дата берётся в таймзоне проекта (Asia/Almaty), чтобы в 04:00 1 марта
           выгружались данные за 28 февраля и сохранялись с date_at=1 марта.
         - work_day_date = вчера по локальной дате; границы дня в локальной таймзоне.
         - Для сохранения в базе используется дата следующего дня: next_day (дата выгрузки).
        """
        days_to_subtract = days if days is not None else settings.DAYS
        local_now = timezone.localtime(timezone.now())
        work_day_date = local_now.date() - timedelta(days=days_to_subtract)
        next_day_date = work_day_date + timedelta(days=1)
        start_date = timezone.make_aware(dt.combine(work_day_date, time.min))
        end_date = timezone.make_aware(
            dt.combine(work_day_date, time(23, 59, 59, 999999))
        )
        next_day = timezone.make_aware(dt.combine(next_day_date, time.min))

        logger.info(
            "Starting get_all_attendance for date range: %s to %s, saving records for date %s",
            start_date.strftime("%Y-%m-%d %H:%M:%S"),
            end_date.strftime("%Y-%m-%d %H:%M:%S"),
            next_day.date(),
        )

        pins = await database_sync_to_async(list)(
            models.Staff.objects.values_list("pin", flat=True)
        )
        total_pins = len(pins)
        logger.info("Found %d active staff pins", total_pins)

        if total_pins == 0:
            logger.warning("No staff pins found. Nothing to fetch.")
            return {
                "days": days_to_subtract,
                "source_date": start_date.date().isoformat(),
                "save_date": next_day.date().isoformat(),
                "total_pins": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "pins_with_events": 0,
                "pins_without_events": 0,
                "created_records": 0,
                "updated_records": 0,
                "event_time_parse_errors": 0,
                "failed_pins": [],
                "errors": [],
            }

        async with self as fetcher:
            logger.info(
                "Using worker pool with max_concurrent_requests=%s",
                self.max_concurrent_requests,
            )
            queue: asyncio.Queue[str] = asyncio.Queue()
            for pin in pins:
                queue.put_nowait(pin)

            results: list[dict[str, Any]] = []
            results_lock = asyncio.Lock()
            processed_counter = 0

            async def process_pin(pin: str) -> dict[str, Any]:
                try:
                    data, error = await fetcher.fetch_attendance(
                        pin, start_date, end_date
                    )
                except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
                    logger.error(
                        "Attendance fetch failed after retries for PIN %s: %s",
                        pin,
                        str(exc),
                    )
                    return {
                        "pin": pin,
                        "data": [],
                        "error": {
                            "pin": pin,
                            "error": f"Network error after retries: {exc}",
                        },
                    }

                if error:
                    return {"pin": pin, "data": [], "error": error}

                if data:
                    logger.debug(
                        "Retrieved %d attendance records for PIN %s", len(data), pin
                    )
                else:
                    logger.info(
                        "No attendance events for PIN %s in requested period", pin
                    )

                return {"pin": pin, "data": data, "error": None}

            async def worker() -> None:
                nonlocal processed_counter
                while True:
                    try:
                        pin = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return

                    result = await process_pin(pin)
                    async with results_lock:
                        results.append(result)
                        processed_counter += 1
                        if (
                            processed_counter % 100 == 0
                            or processed_counter == total_pins
                        ):
                            logger.info(
                                "Attendance fetch progress: %d/%d pins processed",
                                processed_counter,
                                total_pins,
                            )
                    queue.task_done()

            workers = [
                asyncio.create_task(worker())
                for _ in range(self.max_concurrent_requests)
            ]
            await asyncio.gather(*workers)
            logger.info("Completed fetching attendance data for all pins")

        successful_results = [result for result in results if result["error"] is None]
        failed_results = [result for result in results if result["error"] is not None]

        attendance_data = {
            result["pin"]: result["data"] for result in successful_results
        }

        db_update_result = {
            "created_records": 0,
            "updated_records": 0,
            "event_time_parse_errors": 0,
            "ambiguous_exit_candidates": 0,
            "ambiguous_resolved_as_exit": 0,
            "ambiguous_resolved_as_transfer": 0,
        }
        if attendance_data:
            db_update_result = await database_sync_to_async(update_attendance_records)(
                attendance_data, next_day
            )
        else:
            logger.warning(
                "Skipping DB update because no successful responses were received from external API."
            )

        pins_with_events = sum(
            1 for result in successful_results if bool(result["data"])
        )
        pins_without_events = len(successful_results) - pins_with_events
        errors = [result["error"] for result in failed_results if result["error"]]
        failed_pins = [result["pin"] for result in failed_results]

        logger.info(
            "Attendance fetch summary: total=%d, successful=%d, failed=%d, with_events=%d, without_events=%d, created=%d, updated=%d, parse_errors=%d, ambiguous_candidates=%d, ambiguous_exit=%d, ambiguous_transfer=%d",
            total_pins,
            len(successful_results),
            len(failed_results),
            pins_with_events,
            pins_without_events,
            db_update_result["created_records"],
            db_update_result["updated_records"],
            db_update_result["event_time_parse_errors"],
            db_update_result["ambiguous_exit_candidates"],
            db_update_result["ambiguous_resolved_as_exit"],
            db_update_result["ambiguous_resolved_as_transfer"],
        )

        if errors:
            logger.warning(
                "Fetcher completed with errors for %d PIN(s). Check logs for full details.",
                len(errors),
            )

        return {
            "days": days_to_subtract,
            "source_date": start_date.date().isoformat(),
            "save_date": next_day.date().isoformat(),
            "total_pins": total_pins,
            "successful_requests": len(successful_results),
            "failed_requests": len(failed_results),
            "pins_with_events": pins_with_events,
            "pins_without_events": pins_without_events,
            "created_records": db_update_result["created_records"],
            "updated_records": db_update_result["updated_records"],
            "event_time_parse_errors": db_update_result["event_time_parse_errors"],
            "ambiguous_exit_candidates": db_update_result["ambiguous_exit_candidates"],
            "ambiguous_resolved_as_exit": db_update_result[
                "ambiguous_resolved_as_exit"
            ],
            "ambiguous_resolved_as_transfer": db_update_result[
                "ambiguous_resolved_as_transfer"
            ],
            "failed_pins": failed_pins,
            "errors": errors,
        }


def _parse_event_time(ev: Dict[str, Any]):
    """Парсит время события из словаря ответа API СКУД.

    Args:
        ev: Словарь события с ключом "eventTime" (строка в формате ISO или
            "YYYY-MM-DD HH:MM:SS"). Может содержать и другие поля.

    Returns:
        timezone-aware datetime или None при ошибке парсинга или отсутствии ключа.
    """
    try:
        return timezone.make_aware(dt.fromisoformat(ev["eventTime"]))
    except (ValueError, KeyError, TypeError):
        return None


def _compute_attendance_from_events(
    events: List[Dict[str, Any]],
) -> Tuple[
    Optional[dt],
    Optional[dt],
    Optional[int],
    Optional[List[Dict[str, str]]],
    Optional[List[Dict[str, str]]],
    str,
    str,
    Dict[str, int],
]:
    """Считает по событиям СКУД за день границы и эффективное время в здании.

    Устройства из ATTENDANCE_EXIT_DEVICE_SNS считаются выходом только если событие
    не первое за день (первое событие трактуется как приход в здание). Интервалы
    «внутри» между входами и выходами суммируются в effective_work_seconds и
    сохраняются в effective_work_intervals для последующего объединения с LA.

    Args:
        events: Список словарей событий API СКУД (eventTime, areaName, devSn и др.).

    Returns:
        Кортеж из восьми элементов:
            - first_in: datetime первого входа или None.
            - last_out: datetime последнего выхода или None.
            - effective_work_seconds: сумма секунд «в здании» или None.
            - area_sequence: список {"t": "HH:MM", "area": "..."} или None.
            - effective_work_intervals: список {"start": ISO, "end": ISO} или None.
            - area_name_in: строка зоны первого события.
            - area_name_out: строка зоны последнего события.
            - resolution_stats: счетчики по неоднозначным выходам.
    """
    resolution_stats = {
        "ambiguous_exit_candidates": 0,
        "ambiguous_resolved_as_exit": 0,
        "ambiguous_resolved_as_transfer": 0,
    }
    exit_sns = set(
        getattr(
            settings,
            "ATTENDANCE_EXIT_DEVICE_SNS",
            frozenset(),
        )
    )
    ambiguous_exit_sns = set(
        getattr(
            settings,
            "ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS",
            frozenset(),
        )
    )
    reentry_sns = set(
        getattr(
            settings,
            "ATTENDANCE_REENTRY_DEVICE_SNS",
            frozenset(),
        )
    )
    try:
        grace_minutes = max(
            0,
            int(getattr(settings, "ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES", 45)),
        )
    except (TypeError, ValueError):
        grace_minutes = 45
    grace_delta = timedelta(minutes=grace_minutes)

    if not events:
        return (
            None,
            None,
            None,
            None,
            None,
            "Unknown",
            "Unknown",
            resolution_stats,
        )

    sorted_events = sorted(
        events,
        key=lambda e: (e.get("eventTime") or ""),
    )
    parsed_events: List[Tuple[Dict[str, Any], Optional[dt], str, str]] = []
    for ev in sorted_events:
        t_dt = _parse_event_time(ev)
        area = (ev.get("areaName") or "Unknown").strip() or "Unknown"
        dev_sn = (ev.get("devSn") or "").strip()
        parsed_events.append((ev, t_dt, area, dev_sn))

    def resolve_exit_state(
        event_index: int,
        event_time: dt,
        dev_sn: str,
    ) -> Tuple[bool, bool, str]:
        """Resolves whether current event should close an in-building interval."""
        is_exit_candidate = dev_sn in exit_sns and event_index > 0
        if not is_exit_candidate:
            return False, False, ""

        if dev_sn not in ambiguous_exit_sns:
            return True, True, "exit"

        resolution_stats["ambiguous_exit_candidates"] += 1
        threshold = event_time + grace_delta
        for _, next_time, _, next_dev_sn in parsed_events[event_index + 1 :]:
            if next_time is None:
                continue
            if next_time <= event_time:
                continue
            if next_time > threshold:
                break
            if next_dev_sn in reentry_sns:
                resolution_stats["ambiguous_resolved_as_transfer"] += 1
                return False, True, "bridge_transfer"

        resolution_stats["ambiguous_resolved_as_exit"] += 1
        return True, True, "exit"

    area_sequence: List[Dict[str, str]] = []
    intervals_raw: List[Tuple[dt, dt]] = []
    in_start: Optional[dt] = None
    total_seconds = 0
    first_in_dt = None
    last_out_dt = None

    for idx, (_, t_dt, area, dev_sn) in enumerate(parsed_events):
        if t_dt is None:
            continue
        is_exit, is_exit_candidate, exit_resolution = resolve_exit_state(
            idx, t_dt, dev_sn
        )
        item: Dict[str, str] = {"t": t_dt.strftime("%H:%M"), "area": area}
        if dev_sn:
            item["devSn"] = dev_sn
        if is_exit_candidate:
            item["exit_candidate"] = "1"
        if exit_resolution:
            item["exit_resolution"] = exit_resolution
        if is_exit:
            item["is_exit"] = "1"
        area_sequence.append(item)
        if is_exit:
            if in_start is not None:
                delta = int((t_dt - in_start).total_seconds())
                total_seconds += delta
                intervals_raw.append((in_start, t_dt))
                last_out_dt = t_dt
            in_start = None
        else:
            if in_start is None:
                if first_in_dt is None:
                    first_in_dt = t_dt
                in_start = t_dt
            last_out_dt = t_dt

    if in_start is not None and last_out_dt is not None and last_out_dt > in_start:
        delta = int((last_out_dt - in_start).total_seconds())
        total_seconds += delta
        intervals_raw.append((in_start, last_out_dt))

    if first_in_dt is None and sorted_events:
        t0 = _parse_event_time(sorted_events[0])
        if t0:
            first_in_dt = t0
    if last_out_dt is None and sorted_events:
        t1 = _parse_event_time(sorted_events[-1])
        if t1:
            last_out_dt = t1

    area_name_in = (
        sorted_events[0].get("areaName") or "Unknown" if sorted_events else "Unknown"
    )
    area_name_out = (
        sorted_events[-1].get("areaName") or "Unknown" if sorted_events else "Unknown"
    )
    effective = total_seconds if total_seconds > 0 else None
    effective_work_intervals: Optional[List[Dict[str, str]]] = None
    if intervals_raw:
        effective_work_intervals = [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in intervals_raw
        ]
    return (
        first_in_dt,
        last_out_dt,
        effective,
        area_sequence if area_sequence else None,
        effective_work_intervals,
        area_name_in,
        area_name_out,
        resolution_stats,
    )


def update_attendance_records(
    attendance_data: Dict[str, List[Dict[str, Any]]], next_day: dt
) -> Dict[str, int]:
    """Обновляет или создаёт записи StaffAttendance в БД в одной транзакции.

    Ключ записи — next_day.date() (дата выгрузки). По сырым событиям СКУД для
    каждого сотрудника вычисляются first_in, last_out, effective_work_seconds,
    area_sequence и effective_work_intervals через _compute_attendance_from_events.

    Args:
        attendance_data: Словарь {pin: [события API]} по всем сотрудникам за день.
        next_day: datetime даты выгрузки (следующий день после рабочего).

    Returns:
        Словарь с ключами created_records, updated_records,
        event_time_parse_errors и счетчиками ambiguous_*.
    """
    updates = []
    creates = []
    event_time_parse_errors = 0
    ambiguous_exit_candidates = 0
    ambiguous_resolved_as_exit = 0
    ambiguous_resolved_as_transfer = 0

    logger.info("Beginning atomic transaction for database updates")
    with atomic_block():
        existing_qs = models.StaffAttendance.objects.filter(
            date_at=next_day.date()
        ).only(
            "id",
            "staff_id",
            "date_at",
            "first_in",
            "last_out",
            "area_name_in",
            "area_name_out",
            "effective_work_seconds",
            "area_sequence",
            "effective_work_intervals",
        )
        existing_records = {(att.staff_id, att.date_at): att for att in existing_qs}
        logger.info(
            "Found %d existing attendance records for date %s",
            len(existing_records),
            next_day.date(),
        )

        staff_queryset = models.Staff.objects.filter(pin__in=attendance_data.keys())
        for staff in staff_queryset:
            data = attendance_data.get(staff.pin, [])
            if data:
                (
                    first_event_time,
                    last_event_time,
                    effective_work_seconds,
                    area_sequence,
                    effective_work_intervals,
                    area_name_in,
                    area_name_out,
                    resolution_stats,
                ) = _compute_attendance_from_events(data)
                ambiguous_exit_candidates += resolution_stats.get(
                    "ambiguous_exit_candidates", 0
                )
                ambiguous_resolved_as_exit += resolution_stats.get(
                    "ambiguous_resolved_as_exit", 0
                )
                ambiguous_resolved_as_transfer += resolution_stats.get(
                    "ambiguous_resolved_as_transfer", 0
                )
                if first_event_time is None and data:
                    event_time_parse_errors += 1
            else:
                first_event_time = None
                last_event_time = None
                effective_work_seconds = None
                area_sequence = None
                effective_work_intervals = None
                area_name_in = "Unknown"
                area_name_out = "Unknown"
                logger.debug(
                    "No data available for staff PIN %s; using default values.",
                    staff.pin,
                )

            key = (staff.id, next_day.date())
            if key in existing_records:
                att_obj = existing_records[key]
                att_obj.first_in = first_event_time
                att_obj.last_out = last_event_time
                att_obj.area_name_in = area_name_in
                att_obj.area_name_out = area_name_out
                att_obj.effective_work_seconds = effective_work_seconds
                att_obj.area_sequence = area_sequence
                att_obj.effective_work_intervals = effective_work_intervals
                updates.append(att_obj)
                logger.debug(
                    "Scheduled update for attendance record of staff id %s on %s",
                    staff.id,
                    next_day.date(),
                )
            else:
                new_att = models.StaffAttendance(
                    staff=staff,
                    date_at=next_day.date(),
                    first_in=first_event_time,
                    last_out=last_event_time,
                    area_name_in=area_name_in,
                    area_name_out=area_name_out,
                    effective_work_seconds=effective_work_seconds,
                    area_sequence=area_sequence,
                    effective_work_intervals=effective_work_intervals,
                )
                creates.append(new_att)
                logger.debug(
                    "Scheduled creation for attendance record of staff id %s on %s",
                    staff.id,
                    next_day.date(),
                )

        if creates:
            logger.info("Creating %d new attendance records", len(creates))
            models.StaffAttendance.objects.bulk_create(creates)
        if updates:
            logger.info("Updating %d existing attendance records", len(updates))
            models.StaffAttendance.objects.bulk_update(
                updates,
                [
                    "first_in",
                    "last_out",
                    "area_name_in",
                    "area_name_out",
                    "effective_work_seconds",
                    "area_sequence",
                    "effective_work_intervals",
                ],
            )
        logger.info("Completed atomic transaction for attendance records update")

        if creates or updates:
            work_day = next_day.date() - timedelta(days=1)
            work_day_str = work_day.strftime("%Y-%m-%d")
            invalidate_cache_pattern(f"staff_attendance_stats_{work_day_str}*")
            invalidate_cache_pattern(f"map_location_{work_day_str}*")
            invalidate_cache("today_attendance_stats")
            invalidate_cache("map_locations_today")
            invalidate_cache_pattern("staff_detail_*")
            logger.info(
                "Invalidated attendance cache for work_day=%s (date_at=%s)",
                work_day_str,
                next_day.date(),
            )

    return {
        "created_records": len(creates),
        "updated_records": len(updates),
        "event_time_parse_errors": event_time_parse_errors,
        "ambiguous_exit_candidates": ambiguous_exit_candidates,
        "ambiguous_resolved_as_exit": ambiguous_resolved_as_exit,
        "ambiguous_resolved_as_transfer": ambiguous_resolved_as_transfer,
    }
