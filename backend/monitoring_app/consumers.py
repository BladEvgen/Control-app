import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from monitoring_app import models

logger = logging.getLogger(__name__)
photo_ws_logger = logging.getLogger("monitoring_app.photo_verdict")

HEARTBEAT_INTERVAL = 20
PHOTO_UPDATE_FLUSH_DELAY = 0.6
PHOTO_UPDATE_MAX_WAIT = 2.0
PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE = 200
PHOTO_WS_PROTOCOL = "v2"
PAD_SCAN_DEFAULT_FLUSH_DELAY = 0.8
PAD_SCAN_DEFAULT_MAX_WAIT = 2.5
PAD_SCAN_DEFAULT_MAX_ITEMS = 60
PAD_SCAN_DEFAULT_LOCK_TTL = 180
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
        self._pad_scan_queue: dict[int, float] = {}
        self._pad_scan_task = None
        self._pad_last_event_ts = 0.0
        self._pad_device = "auto"
        self._send_legacy_photos = True
        self._risk_only = False
        self._visible_ids: set[int] = set()
        self._pad_scan_enabled = self._parse_bool_setting(
            getattr(settings, "PHOTO_PAD_WS_SCAN_ENABLED", True),
            default=True,
        )
        self._pad_scan_flush_delay = self._parse_float_setting(
            getattr(
                settings,
                "PHOTO_PAD_WS_SCAN_FLUSH_DELAY",
                PAD_SCAN_DEFAULT_FLUSH_DELAY,
            ),
            default=PAD_SCAN_DEFAULT_FLUSH_DELAY,
            minimum=0.1,
        )
        self._pad_scan_max_wait = self._parse_float_setting(
            getattr(
                settings,
                "PHOTO_PAD_WS_SCAN_MAX_WAIT",
                PAD_SCAN_DEFAULT_MAX_WAIT,
            ),
            default=PAD_SCAN_DEFAULT_MAX_WAIT,
            minimum=self._pad_scan_flush_delay,
        )
        self._pad_scan_max_items = self._parse_int_setting(
            getattr(
                settings,
                "PHOTO_PAD_WS_SCAN_MAX_ITEMS",
                PAD_SCAN_DEFAULT_MAX_ITEMS,
            ),
            default=PAD_SCAN_DEFAULT_MAX_ITEMS,
            minimum=1,
        )
        self._pad_scan_lock_ttl = self._parse_int_setting(
            getattr(
                settings,
                "PHOTO_PAD_WS_SCAN_LOCK_TTL",
                PAD_SCAN_DEFAULT_LOCK_TTL,
            ),
            default=PAD_SCAN_DEFAULT_LOCK_TTL,
            minimum=10,
        )
        try:
            from monitoring_app.photo_pad import normalize_device

            self._pad_device = normalize_device(
                getattr(settings, "PHOTO_PAD_DEVICE", "auto")
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize PAD runtime settings for PhotoConsumer: %s",
                exc,
            )
            self._pad_scan_enabled = False

    @staticmethod
    def _parse_bool_setting(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _parse_int_setting(value: Any, *, default: int, minimum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, parsed)

    @staticmethod
    def _parse_float_setting(value: Any, *, default: float, minimum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, parsed)

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
        legacy_param = str(params.get("legacy", "1")).strip().lower()
        self._send_legacy_photos = legacy_param not in {"0", "false", "no", "off"}
        risk_only_param = str(params.get("risk_only", "0")).strip().lower()
        self._risk_only = risk_only_param in {"1", "true", "yes", "on", "y"}
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
        if self._pad_scan_task and not self._pad_scan_task.done():
            self._pad_scan_task.cancel()
            try:
                await self._pad_scan_task
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
            if self._photo_flush_task and not self._photo_flush_task.done():
                self._photo_flush_task.cancel()
                try:
                    await self._photo_flush_task
                except asyncio.CancelledError:
                    pass
            if self._pad_scan_task and not self._pad_scan_task.done():
                self._pad_scan_task.cancel()
                try:
                    await self._pad_scan_task
                except asyncio.CancelledError:
                    pass
            self.group_name = f"photos_{new_date}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.date = new_date
            self._photo_update_buffer.clear()
            self._pad_scan_queue.clear()
            self._visible_ids.clear()

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
            "photoSpoofStatus": record.photo_spoof_status,
            "photoManualVerdict": record.photo_manual_verdict,
            "photoCanSetManualVerdict": record.photo_can_set_manual_verdict,
        }

    def _photo_payload_to_event(
        self,
        photo_payload: dict[str, Any],
        *,
        op: str,
        state_code: str | None = None,
        version_ts: str | None = None,
    ) -> dict[str, Any]:
        normalized_op = (
            op if op in {"snapshot", "created", "updated", "deleted"} else "updated"
        )
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
        if self._send_legacy_photos:
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
        filtered_photos = photos
        if self._risk_only:
            filtered_photos = [
                photo
                for photo in photos
                if self._is_risk_candidate(photo)
            ]
            self._visible_ids = {
                int(photo["id"])
                for photo in filtered_photos
                if photo.get("id") is not None
            }
        else:
            self._visible_ids.clear()
        snapshot_ts = timezone.now().isoformat()
        events = [
            self._photo_payload_to_event(
                photo,
                op="snapshot",
                state_code=STATE_SNAPSHOT,
                version_ts=snapshot_ts,
            )
            for photo in filtered_photos
        ]
        await self._send_batched_events(message_type="initial_photos", events=events)
        self._queue_pad_scan_ids(
            [
                int(photo["id"])
                for photo in photos
                if photo.get("id") is not None and self._is_pad_scan_candidate(photo)
            ]
        )

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
                    "photo_spoof_status",
                    "photo_manual_verdict",
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
        attendance_ids = self._extract_event_attendance_ids(event)
        if not attendance_ids:
            photo_ws_logger.error(
                "attendance_id(s) not found in event new_photo/attendance_deleted event=%s",
                event,
            )
            return
        op = str(event.get("op") or "updated").lower()
        if op not in {"created", "updated", "deleted", "snapshot"}:
            op = "updated"
        version_ts = event.get("versionTs") or timezone.now().isoformat()
        for normalized_id in attendance_ids:
            self._photo_update_buffer[normalized_id] = {
                "id": normalized_id,
                "op": op,
                "stateCode": event.get("stateCode"),
                "versionTs": version_ts,
            }
        self._photo_last_event_ts = asyncio.get_running_loop().time()
        if self._photo_flush_task is None or self._photo_flush_task.done():
            self._photo_flush_task = asyncio.create_task(
                self._flush_photo_updates_after_delay()
            )
        if op != "deleted":
            self._queue_pad_scan_ids(attendance_ids)

    @staticmethod
    def _extract_event_attendance_ids(event: dict[str, Any]) -> list[int]:
        raw_ids = event.get("attendance_ids")
        candidates: list[Any] = []
        if isinstance(raw_ids, (list, tuple, set)):
            candidates.extend(list(raw_ids))
        single_id = event.get("attendance_id")
        if single_id is not None:
            candidates.append(single_id)

        parsed_ids: list[int] = []
        seen: set[int] = set()
        for value in candidates:
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                continue
            if normalized <= 0 or normalized in seen:
                continue
            seen.add(normalized)
            parsed_ids.append(normalized)
        return parsed_ids

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
        upsert_ids = [
            meta["id"] for meta in pending_meta if meta.get("op") != "deleted"
        ]
        events: list[dict[str, Any]] = []
        candidate_scan_ids: list[int] = []
        try:
            fetched_photos = await self.get_photo_data_bulk(upsert_ids)
            fetched_by_id = {
                photo["id"]: photo for photo in fetched_photos if photo.get("id")
            }

            for attendance_id in ordered_ids:
                meta = meta_by_id.get(attendance_id, {})
                op = str(meta.get("op") or "updated")
                version_ts = str(meta.get("versionTs") or timezone.now().isoformat())
                state_code = (
                    str(meta.get("stateCode"))
                    if meta.get("stateCode") is not None
                    else None
                )
                was_visible = attendance_id in self._visible_ids
                if op == "deleted":
                    if self._risk_only:
                        if was_visible:
                            events.append(
                                {
                                    "id": attendance_id,
                                    "op": "deleted",
                                    "stateCode": STATE_DELETED,
                                    "versionTs": version_ts,
                                }
                            )
                        self._visible_ids.discard(attendance_id)
                    else:
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
                    photo_ws_logger.warning(
                        "photos_updated: record not in DB attendance_id=%s ordered_ids=%s",
                        attendance_id,
                        ordered_ids[:20],
                    )
                    if self._risk_only:
                        if was_visible:
                            events.append(
                                {
                                    "id": attendance_id,
                                    "op": "deleted",
                                    "stateCode": STATE_DELETED,
                                    "versionTs": version_ts,
                                }
                            )
                        self._visible_ids.discard(attendance_id)
                    else:
                        events.append(
                            {
                                "id": attendance_id,
                                "op": "deleted",
                                "stateCode": STATE_DELETED,
                                "versionTs": version_ts,
                            }
                        )
                    continue
                normalized_event = self._photo_payload_to_event(
                    photo_payload,
                    op=op,
                    state_code=state_code,
                    version_ts=version_ts,
                )
                if self._risk_only:
                    is_risk_candidate = self._is_risk_candidate(photo_payload)
                    if is_risk_candidate:
                        events.append(normalized_event)
                        self._visible_ids.add(attendance_id)
                    elif was_visible:
                        events.append(
                            {
                                "id": attendance_id,
                                "op": "deleted",
                                "stateCode": STATE_DELETED,
                                "versionTs": version_ts,
                            }
                        )
                        self._visible_ids.discard(attendance_id)
                else:
                    events.append(normalized_event)
                if self._is_pad_scan_candidate(photo_payload):
                    candidate_scan_ids.append(attendance_id)
            await self._send_batched_events(
                message_type="photos_updated", events=events
            )
            if not events and ordered_ids:
                photo_ws_logger.warning(
                    "photos_updated: empty events after filter (risk_only=%s) ordered_ids=%s",
                    self._risk_only,
                    ordered_ids[:20],
                )
            photo_ws_logger.info(
                "photos_updated sent to client count=%s ids=%s",
                len(events),
                ordered_ids[:10] if len(ordered_ids) > 10 else ordered_ids,
            )
            self._queue_pad_scan_ids(candidate_scan_ids)
        except Exception as e:
            photo_ws_logger.warning(
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

    def _is_pad_scan_candidate(self, photo_payload: dict[str, Any]) -> bool:
        if not self._pad_scan_enabled:
            return False
        if not bool(photo_payload.get("hasPhoto")):
            return False
        manual_verdict = str(photo_payload.get("photoManualVerdict") or "")
        if manual_verdict != models.LessonAttendance.PHOTO_MANUAL_VERDICT_NONE:
            return False
        status = str(photo_payload.get("photoSpoofStatus") or "")
        return status == models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING

    @staticmethod
    def _is_risk_candidate(photo_payload: dict[str, Any]) -> bool:
        manual_verdict = str(
            photo_payload.get("photoManualVerdict")
            or models.LessonAttendance.PHOTO_MANUAL_VERDICT_NONE
        )
        if manual_verdict == models.LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS:
            return True
        if manual_verdict == models.LessonAttendance.PHOTO_MANUAL_VERDICT_CLEAN:
            return False
        status = str(
            photo_payload.get("photoSpoofStatus")
            or models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING
        )
        return status in {
            models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING,
            models.LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW,
            models.LessonAttendance.PHOTO_SPOOF_STATUS_ERROR,
            models.LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
        }

    def _queue_pad_scan_ids(self, attendance_ids: list[int]) -> None:
        if not self._pad_scan_enabled or not attendance_ids:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        added_any = False
        for attendance_id in attendance_ids:
            if attendance_id <= 0:
                continue
            if attendance_id not in self._pad_scan_queue:
                self._pad_scan_queue[attendance_id] = now
                added_any = True
        if not added_any:
            return
        self._pad_last_event_ts = now
        if self._pad_scan_task is None or self._pad_scan_task.done():
            self._pad_scan_task = asyncio.create_task(
                self._flush_pad_scan_after_delay()
            )

    async def _flush_pad_scan_after_delay(self) -> None:
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        while True:
            await asyncio.sleep(self._pad_scan_flush_delay)
            now = loop.time()
            quiet_for = now - self._pad_last_event_ts
            waited = now - started_at
            if (
                quiet_for >= self._pad_scan_flush_delay
                or waited >= self._pad_scan_max_wait
            ):
                break
        await self._flush_pad_scan()

    async def _flush_pad_scan(self) -> None:
        if not self._pad_scan_enabled:
            self._pad_scan_queue.clear()
            self._pad_scan_task = None
            return
        if not self._pad_scan_queue:
            self._pad_scan_task = None
            return

        batch_ids = list(self._pad_scan_queue.keys())[: self._pad_scan_max_items]
        for attendance_id in batch_ids:
            self._pad_scan_queue.pop(attendance_id, None)

        changed_ids: list[int] = []
        try:
            changed_ids = await sync_to_async(
                self._scan_and_update_attendance_ids,
                thread_sensitive=False,
            )(batch_ids)
        except Exception as exc:
            logger.exception(
                "PAD websocket batch scan failed ids=%s error=%s", batch_ids, exc
            )
            photo_ws_logger.exception(
                "PAD websocket batch scan failed ids=%s error=%s", batch_ids, exc
            )

        if changed_ids:
            await self._broadcast_scanned_updates(changed_ids)

        if self._pad_scan_queue:
            self._pad_scan_task = asyncio.create_task(
                self._flush_pad_scan_after_delay()
            )
        else:
            self._pad_scan_task = None

    def _scan_and_update_attendance_ids(self, attendance_ids: list[int]) -> list[int]:
        if not attendance_ids:
            return []

        from monitoring_app.photo_pad import MANUAL_NONE, PAD_MODEL_VERSION, check_photo

        id_order = {
            attendance_id: idx for idx, attendance_id in enumerate(attendance_ids)
        }
        records = list(
            models.LessonAttendance.objects.filter(id__in=attendance_ids).only(
                "id",
                "staff_image_path",
                "photo_manual_verdict",
                "photo_spoof_status",
                "photo_spoof_checked_at",
                "photo_spoof_model_version",
            )
        )
        records.sort(key=lambda record: id_order.get(record.id, 10**9))

        changed_ids: list[int] = []
        for record in records:
            image_path = record.staff_image_path
            if not image_path:
                continue
            if record.photo_manual_verdict != MANUAL_NONE:
                continue
            if (
                record.photo_spoof_status
                != models.LessonAttendance.PHOTO_SPOOF_STATUS_PENDING
                and record.photo_spoof_checked_at is not None
                and record.photo_spoof_model_version == PAD_MODEL_VERSION
            ):
                continue

            lock_key = f"photo_pad_scan_lock:{record.id}"
            acquired = cache.add(
                lock_key,
                timezone.now().isoformat(),
                timeout=self._pad_scan_lock_ttl,
            )
            if not acquired:
                continue
            try:
                result = check_photo(image_path=image_path, device=self._pad_device)
            except Exception:
                logger.exception(
                    "PAD websocket scan failed for id=%s path=%s",
                    record.id,
                    image_path,
                )
                photo_ws_logger.exception(
                    "PAD websocket scan failed for id=%s path=%s",
                    record.id,
                    image_path,
                )
                continue
            finally:
                cache.delete(lock_key)

            update_kwargs = result.to_update_kwargs()
            updated_rows = models.LessonAttendance.objects.filter(
                id=record.id,
                photo_manual_verdict=MANUAL_NONE,
            ).update(**update_kwargs)
            if updated_rows:
                changed_ids.append(record.id)
        return changed_ids

    async def _broadcast_scanned_updates(self, attendance_ids: list[int]) -> None:
        if not attendance_ids:
            return
        version_ts = timezone.now().isoformat()
        unique_ids = list(dict.fromkeys(attendance_ids))
        for start in range(0, len(unique_ids), PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE):
            chunk = unique_ids[start : start + PHOTO_UPDATE_MAX_ITEMS_PER_MESSAGE]
            event_payload: dict[str, Any] = {
                "type": "new_photo",
                "attendance_ids": chunk,
                "op": "updated",
                "stateCode": STATE_UPDATED_META,
                "versionTs": version_ts,
            }
            if len(chunk) == 1:
                event_payload["attendance_id"] = chunk[0]
            await self.channel_layer.group_send(self.group_name, event_payload)

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
                    "photo_spoof_status",
                    "photo_manual_verdict",
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
                "photo_spoof_status",
                "photo_manual_verdict",
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
