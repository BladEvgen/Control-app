import asyncio
import aiohttp
import backoff
import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from monitoring_app import models
from django.core.cache import cache
from typing import Dict, List, Optional
from channels.db import database_sync_to_async

logger = logging.getLogger("django")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="113", "Chromium";v="113", "Not-A.Brand";v="24"',
    "sec-ch-ua-platform": '"Windows"',
}
class AsyncAttendanceFetcher:
    def __init__(self, chunk_size: int = 50, max_concurrent_requests: int = 6):
        self.chunk_size = chunk_size
        self.max_concurrent_requests = max_concurrent_requests
        self.session = None
        logger.info(
            "AsyncAttendanceFetcher initialized with chunk_size=%s and max_concurrent_requests=%s",
            self.chunk_size,
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
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3,
    )
    async def fetch_attendance(
        self, pin: str, start_date: datetime, end_date: datetime
    ) -> List[Dict]:
        cache_key = f"attendance:{pin}:{start_date.date()}:{end_date.date()}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.info(
                "Cache hit for PIN %s on %s to %s",
                pin,
                start_date.date(),
                end_date.date(),
            )
            return cached_data

        params = {
            "endDate": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "pageNo": "1",
            "pageSize": "1000",
            "personPin": pin,
            "startDate": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "access_token": settings.API_KEY,
        }
        logger.info("Fetching attendance for PIN %s", pin)

        try:
            async with self.session.get(
                settings.API_URL + "/api/transaction/listAttTransaction",
                params=params,
                headers=BROWSER_HEADERS,
                ssl=True,
            ) as response:
                logger.info(
                    "Received response for PIN %s with status %s", pin, response.status
                )
                response.raise_for_status()
                data = await response.json()
                result = data.get("data", [])
                cache.set(cache_key, result, 600)
                logger.info(
                    "Fetched attendance for PIN %s. Caching result for 10 minutes.", pin
                )
                return result
        except Exception as e:
            logger.error(
                "Error fetching attendance for PIN %s: %s", pin, str(e), exc_info=True
            )
            return []

    async def get_all_attendance(self, days: Optional[int] = None) -> None:
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
        logger.info("Found %d active staff pins", len(pins))

        async with self as fetcher:
            sem = asyncio.Semaphore(self.max_concurrent_requests)
            logger.info(
                "Using semaphore with max_concurrent_requests=%s",
                self.max_concurrent_requests,
            )

            async def process_pin(pin):
                async with sem:
                    logger.info("Processing PIN: %s", pin)
                    data = await fetcher.fetch_attendance(pin, start_date, end_date)
                    if not data:
                        logger.warning("No attendance data returned for PIN %s", pin)
                    else:
                        logger.info(
                            "Retrieved %d attendance records for PIN %s", len(data), pin
                        )
                    return pin, data

            tasks = [process_pin(pin) for pin in pins]
            results = await asyncio.gather(*tasks)
            attendance_data = dict(results)
            logger.info("Completed fetching attendance data for all pins")

        await database_sync_to_async(update_attendance_records)(attendance_data, next_day)


def update_attendance_records(attendance_data: Dict, next_day: datetime) -> None:
    """
    Синхронная функция для обновления базы данных в атомарной транзакции.
    В качестве ключа для записи используется next_day.date(), как в оригинальной версии.
    """
    updates = []
    creates = []

    logger.info("Beginning atomic transaction for database updates")
    with transaction.atomic():
        existing_qs = models.StaffAttendance.objects.filter(date_at=next_day.date())
        existing_records = {
            (att.staff_id, att.date_at): att for att in existing_qs
        }
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
                        datetime.fromisoformat(first_event["eventTime"])
                    )
                    last_event_time = (
                        timezone.make_aware(datetime.fromisoformat(last_event["eventTime"]))
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
                    first_event_time = None
                    last_event_time = None

                area_name_in = first_event.get("areaName") or "Unknown"
                area_name_out = last_event.get("areaName") or "Unknown"
            else:
                logger.warning(
                    "No data available for staff PIN %s; using default values.", staff.pin
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
                logger.info(
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
                logger.info(
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
