import asyncio
import logging
from contextlib import AbstractContextManager
from datetime import datetime as dt
from datetime import timedelta
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
         - Вычисляется дата, за которую собираются данные: prev_date = timezone.now() - days_to_subtract
         - Границы дня: start_date (начало дня, 00:00:00) и end_date (конец дня, 23:59:59)
         - Для сохранения в базе используется дата следующего дня: next_day = prev_date + 1 день
        """
        days_to_subtract = days if days is not None else settings.DAYS
        prev_date = timezone.now() - timezone.timedelta(days=days_to_subtract)
        start_date = prev_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = prev_date.replace(hour=23, minute=59, second=59, microsecond=0)
        next_day = prev_date + timezone.timedelta(days=1)

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
            "Attendance fetch summary: total=%d, successful=%d, failed=%d, with_events=%d, without_events=%d, created=%d, updated=%d, parse_errors=%d",
            total_pins,
            len(successful_results),
            len(failed_results),
            pins_with_events,
            pins_without_events,
            db_update_result["created_records"],
            db_update_result["updated_records"],
            db_update_result["event_time_parse_errors"],
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
            "failed_pins": failed_pins,
            "errors": errors,
        }


def update_attendance_records(
    attendance_data: Dict[str, List[Dict[str, Any]]], next_day: dt
) -> Dict[str, int]:
    """
    Синхронная функция для обновления базы данных в атомарной транзакции.
    В качестве ключа для записи используется next_day.date(), как в оригинальной версии.
    """
    updates = []
    creates = []
    event_time_parse_errors = 0

    logger.info("Beginning atomic transaction for database updates")
    with atomic_block():
        existing_qs = models.StaffAttendance.objects.filter(date_at=next_day.date())
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
                first_event = data[-1]
                last_event = data[0] if len(data) > 1 else first_event

                try:
                    first_event_time = timezone.make_aware(
                        dt.fromisoformat(first_event["eventTime"])
                    )
                    last_event_time = (
                        timezone.make_aware(dt.fromisoformat(last_event["eventTime"]))
                        if len(data) > 1
                        else first_event_time
                    )
                except Exception as e:
                    logger.error(
                        "Error parsing event times for staff PIN %s: %s",
                        staff.pin,
                        str(e),
                        exc_info=True,
                    )
                    event_time_parse_errors += 1
                    first_event_time = None
                    last_event_time = None

                area_name_in = first_event.get("areaName") or "Unknown"
                area_name_out = last_event.get("areaName") or "Unknown"
            else:
                logger.debug(
                    "No data available for staff PIN %s; using default values.",
                    staff.pin,
                )
                first_event_time = None
                last_event_time = None
                area_name_in = "Unknown"
                area_name_out = "Unknown"

            key = (staff.id, next_day.date())
            if key in existing_records:
                att_obj = existing_records[key]
                att_obj.first_in = first_event_time
                att_obj.last_out = last_event_time
                att_obj.area_name_in = area_name_in
                att_obj.area_name_out = area_name_out
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
                ["first_in", "last_out", "area_name_in", "area_name_out"],
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
    }
