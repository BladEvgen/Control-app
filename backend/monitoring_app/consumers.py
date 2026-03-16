import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone
from monitoring_app import models

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20
PHOTO_UPDATE_FLUSH_DELAY = 0.6
PHOTO_UPDATE_MAX_WAIT = 2.0
PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE = 200
PHOTO_WS_PROTOCOL = "v2"
STATE_SNAPSHOT = "SNAPSHOT"
STATE_CREATED_NO_PHOTO = "CREATED_NO_PHOTO"
STATE_PHOTO_ATTACHED = "PHOTO_ATTACHED"
STATE_UPDATED_META = "UPDATED_META"
STATE_DELETED = "DELETED"


class PhotoConsumer(AsyncJsonWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.date = timezone.now().date()
        self.group_name = ""
        self._heartbeat_task = None
        self._photo_update_buffer: dict[int, dict[str, Any]] = {}
        self._photo_flush_task = None
        self._photo_last_event_ts = 0.0

    async def _heartbeat_loop(self):
        """Периодическая отправка heartbeat для поддержания соединения."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self.send_json(
                    {
                        "type": "heartbeat",
                        "timestamp": timezone.now().isoformat(),
                    }
                )
                logger.debug("Sent heartbeat to client")
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.warning("Heartbeat error: %s", e)

    async def connect(self):
        query_params = self.scope["query_string"].decode()
        params = dict(
            param.split("=") for param in query_params.split("&") if "=" in param
        )
        date_str = params.get("date")
        if date_str:
            try:
                self.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                self.date = timezone.now().date()
        else:
            self.date = timezone.now().date()

        self.group_name = f"photos_{self.date}"

        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        logger.info(f"Client connected and joined group {self.group_name}")

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        await self._send_initial_snapshot()

    async def disconnect(self, _close_code):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._photo_flush_task and not self._photo_flush_task.done():
            self._photo_flush_task.cancel()
            try:
                await self._photo_flush_task
            except asyncio.CancelledError:
                pass
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"Client disconnected and left group {self.group_name}")

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json(
                {"type": "pong", "timestamp": timezone.now().isoformat()}
            )
            logger.debug("Received ping, sent pong")
            return

        if "date" in content:
            new_date_str = content["date"]
            try:
                new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            except ValueError:
                await self.send_json({"error": "Invalid date format"})
                return

            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            self.group_name = f"photos_{new_date}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.date = new_date

            await self._send_initial_snapshot()
            logger.info(f"Client switched to group {self.group_name}")

    @staticmethod
    def _resolve_event_state(
        *,
        has_photo: bool,
        op: str,
        state_override: str | None = None,
    ) -> str:
        if state_override:
            return state_override
        if op == "snapshot":
            return STATE_SNAPSHOT
        if op == "deleted":
            return STATE_DELETED
        if op == "created":
            return STATE_PHOTO_ATTACHED if has_photo else STATE_CREATED_NO_PHOTO
        if has_photo:
            return STATE_PHOTO_ATTACHED
        return STATE_UPDATED_META

    @staticmethod
    def _record_to_photo_payload(record):
        """Собирает payload для одной записи (включая записи без фото)."""
        has_photo = bool(record.staff_image_path)
        return {
            "id": record.id,
            "hasPhoto": has_photo,
            "staffPin": record.staff.pin,
            "staffFullName": f"{record.staff.surname} {record.staff.name}",
            "department": (
                record.staff.department.name if record.staff.department else "Unknown"
            ),
            "photoUrl": record.image_url,
            "attendanceTime": timezone.localtime(record.first_in).isoformat(),
            "tutorInfo": record.tutor_info,
        }

    def _photo_payload_to_event(
        self,
        photo_payload: dict[str, Any],
        *,
        op: str,
        state_code: str | None = None,
        version_ts: str | None = None,
    ) -> dict[str, Any]:
        normalized_op = op if op in {"snapshot", "created", "updated", "deleted"} else "updated"
        resolved_state = self._resolve_event_state(
            has_photo=bool(photo_payload.get("hasPhoto")),
            op=normalized_op,
            state_override=state_code,
        )
        return {
            **photo_payload,
            "op": normalized_op,
            "stateCode": resolved_state,
            "versionTs": version_ts or timezone.now().isoformat(),
        }

    @staticmethod
    def _event_to_legacy_photo(event_payload: dict[str, Any]) -> dict[str, Any] | None:
        if event_payload.get("stateCode") == STATE_DELETED:
            return None
        return {
            "id": event_payload.get("id"),
            "hasPhoto": event_payload.get("hasPhoto"),
            "staffPin": event_payload.get("staffPin"),
            "staffFullName": event_payload.get("staffFullName"),
            "department": event_payload.get("department"),
            "photoUrl": event_payload.get("photoUrl"),
            "attendanceTime": event_payload.get("attendanceTime"),
            "tutorInfo": event_payload.get("tutorInfo"),
        }

    def _build_ws_envelope(
        self,
        *,
        message_type: str,
        events: list[dict[str, Any]],
        batch_id: str,
        chunk_index: int,
        total_chunks: int,
        sent_at: str,
    ) -> dict[str, Any]:
        legacy_photos = []
        for event_payload in events:
            legacy_item = self._event_to_legacy_photo(event_payload)
            if legacy_item is not None:
                legacy_photos.append(legacy_item)
        return {
            "type": message_type,
            "protocol": PHOTO_WS_PROTOCOL,
            "batchId": batch_id,
            "chunkIndex": chunk_index,
            "totalChunks": total_chunks,
            "sentAt": sent_at,
            "events": events,
            "photos": legacy_photos,
        }

    async def _send_batched_events(
        self,
        *,
        message_type: str,
        events: list[dict[str, Any]],
    ) -> None:
        sent_at = timezone.now().isoformat()
        batch_id = uuid.uuid4().hex
        if not events:
            await self.send_json(
                self._build_ws_envelope(
                    message_type=message_type,
                    events=[],
                    batch_id=batch_id,
                    chunk_index=1,
                    total_chunks=1,
                    sent_at=sent_at,
                )
            )
            return
        total_chunks = (
            len(events) + PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE - 1
        ) // PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE
        for chunk_idx in range(total_chunks):
            start = chunk_idx * PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE
            end = start + PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE
            await self.send_json(
                self._build_ws_envelope(
                    message_type=message_type,
                    events=events[start:end],
                    batch_id=batch_id,
                    chunk_index=chunk_idx + 1,
                    total_chunks=total_chunks,
                    sent_at=sent_at,
                )
            )

    async def _send_initial_snapshot(self):
        photos = await self.get_photos_for_date(self.date)
        snapshot_ts = timezone.now().isoformat()
        events = [
            self._photo_payload_to_event(
                photo,
                op="snapshot",
                state_code=STATE_SNAPSHOT,
                version_ts=snapshot_ts,
            )
            for photo in photos
        ]
        await self._send_batched_events(message_type="initial_photos", events=events)

    @sync_to_async
    def get_photos_for_date(self, date):
        """
        Получаем список фотографий для заданной даты.
        Используем кэш, чтобы снизить нагрузку при повторных запросах.
        """
        cache_key = f"photos_for_{date}"
        photos = cache.get(cache_key)
        if photos is None:
            qs = (
                models.LessonAttendance.objects.filter(date_at=date)
                .select_related("staff__department")
                .only(
                    "id",
                    "first_in",
                    "staff_image_path",
                    "tutor",
                    "tutor_id",
                    "subject_name",
                    "staff__pin",
                    "staff__surname",
                    "staff__name",
                    "staff__department__name",
                )
                .order_by("-first_in", "-id")
            )
            photos = []
            for record in qs:
                photos.append(self._record_to_photo_payload(record))
            cache.set(cache_key, photos, timeout=60)
        return photos

    async def new_photo(self, event):
        """
        Обработчик события из channel_layer.group_send.
        Накапливает attendance_id в буфер и по истечении PHOTO_UPDATE_FLUSH_DELAY
        отправляет одним сообщением photos_updated (bulk), чтобы не слать по одному
        при массовом обновлении (одна фотка на много записей и т.п.).
        """
        self._queue_photo_event(event)

    async def attendance_deleted(self, event):
        """Явный обработчик удаления записи."""
        self._queue_photo_event(event)

    def _queue_photo_event(self, event: dict[str, Any]) -> None:
        attendance_id = event.get("attendance_id")
        if not attendance_id:
            logger.error("attendance_id не найден в событии new_photo/attendance_deleted")
            return
        try:
            normalized_id = int(attendance_id)
        except (TypeError, ValueError):
            logger.error("invalid attendance_id in event: %s", attendance_id)
            return
        op = str(event.get("op") or "updated").lower()
        if op not in {"created", "updated", "deleted", "snapshot"}:
            op = "updated"
        self._photo_update_buffer[normalized_id] = {
            "id": normalized_id,
            "op": op,
            "stateCode": event.get("stateCode"),
            "versionTs": event.get("versionTs") or timezone.now().isoformat(),
        }
        self._photo_last_event_ts = asyncio.get_running_loop().time()
        if self._photo_flush_task is None or self._photo_flush_task.done():
            self._photo_flush_task = asyncio.create_task(
                self._flush_photo_updates_after_delay()
            )

    async def _flush_photo_updates_after_delay(self):
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        while True:
            await asyncio.sleep(PHOTO_UPDATE_FLUSH_DELAY)
            now = loop.time()
            quiet_for = now - self._photo_last_event_ts
            waited = now - started_at
            if quiet_for >= PHOTO_UPDATE_FLUSH_DELAY or waited >= PHOTO_UPDATE_MAX_WAIT:
                break
        await self._flush_photo_updates()

    async def _flush_photo_updates(self):
        pending_meta = list(self._photo_update_buffer.values())
        self._photo_update_buffer.clear()
        if not pending_meta:
            self._photo_flush_task = None
            return
        ordered_ids = [meta["id"] for meta in pending_meta]
        meta_by_id = {meta["id"]: meta for meta in pending_meta}
        upsert_ids = [meta["id"] for meta in pending_meta if meta.get("op") != "deleted"]
        events: list[dict[str, Any]] = []
        try:
            fetched_photos = await self.get_photo_data_bulk(upsert_ids)
            fetched_by_id = {photo["id"]: photo for photo in fetched_photos if photo.get("id")}

            for attendance_id in ordered_ids:
                meta = meta_by_id.get(attendance_id, {})
                op = str(meta.get("op") or "updated")
                version_ts = str(meta.get("versionTs") or timezone.now().isoformat())
                state_code = (
                    str(meta.get("stateCode")) if meta.get("stateCode") is not None else None
                )
                if op == "deleted":
                    events.append(
                        {
                            "id": attendance_id,
                            "op": "deleted",
                            "stateCode": STATE_DELETED,
                            "versionTs": version_ts,
                        }
                    )
                    continue
                photo_payload = fetched_by_id.get(attendance_id)
                if photo_payload is None:
                    events.append(
                        {
                            "id": attendance_id,
                            "op": "deleted",
                            "stateCode": STATE_DELETED,
                            "versionTs": version_ts,
                        }
                    )
                    continue
                events.append(
                    self._photo_payload_to_event(
                        photo_payload,
                        op=op,
                        state_code=state_code,
                        version_ts=version_ts,
                    )
                )
            await self._send_batched_events(message_type="photos_updated", events=events)
            logger.info(
                "Sent photos_updated events to client, count=%s ids=%s",
                len(events),
                ordered_ids[:10] if len(ordered_ids) > 10 else ordered_ids,
            )
        except Exception as e:
            logger.warning(
                "Failed to send photos_updated (connection may be closed): %s",
                e,
            )
        finally:
            if self._photo_update_buffer:
                self._photo_flush_task = asyncio.create_task(
                    self._flush_photo_updates_after_delay()
                )
            else:
                self._photo_flush_task = None

    @sync_to_async
    def get_photo_data(self, attendance_id):
        try:
            record = (
                models.LessonAttendance.objects.select_related("staff__department")
                .only(
                    "id",
                    "first_in",
                    "staff_image_path",
                    "tutor",
                    "tutor_id",
                    "subject_name",
                    "staff__pin",
                    "staff__surname",
                    "staff__name",
                    "staff__department__name",
                )
                .get(id=attendance_id)
            )
            return self._record_to_photo_payload(record)
        except models.LessonAttendance.DoesNotExist:
            logger.error("LessonAttendance with id %s does not exist", attendance_id)
            return None

    @sync_to_async
    def get_photo_data_bulk(self, attendance_ids):
        """Один запрос в БД для списка id; возвращает payload, включая записи без фото."""
        if not attendance_ids:
            return []
        qs = (
            models.LessonAttendance.objects.filter(id__in=attendance_ids)
            .select_related("staff__department")
            .only(
                "id",
                "first_in",
                "staff_image_path",
                "tutor",
                "tutor_id",
                "subject_name",
                "staff__pin",
                "staff__surname",
                "staff__name",
                "staff__department__name",
            )
        )
        id_order = {aid: i for i, aid in enumerate(attendance_ids)}
        records = sorted(qs, key=lambda r: id_order.get(r.id, 999999))
        result = []
        for record in records:
            result.append(self._record_to_photo_payload(record))
        return result
