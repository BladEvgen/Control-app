import base64
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from monitoring_app.attendance_fetcher import _compute_attendance_from_events
from monitoring_app.consumers import (
    PHOTO_WS_PROTOCOL,
    STATE_CREATED_NO_PHOTO,
    STATE_DELETED,
    STATE_PHOTO_ATTACHED,
    PhotoConsumer,
)
from monitoring_app.models import APIKey, LessonAttendance, RemoteWork, Staff
from monitoring_app import signals as lesson_signals, tasks as monitoring_tasks
from monitoring_app.views import get_staff_detail
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()


class RemoteWorkAdminTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")
        self.remote_work = RemoteWork.objects.create(
            staff=self.staff, permanent_remote=True
        )

    def test_get_remote_status(self):
        self.assertEqual(
            self.remote_work.get_remote_status(), "Постоянная дистанционная работа"
        )


class StaffDetailTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")

    def test_get_staff_detail(self):
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)
        detail = get_staff_detail(self.staff, start_date, end_date)
        self.assertIn("contract_type", detail)
        self.assertIn("salary", detail)


class LessonTaskStatusTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.staff = Staff.objects.create(name="John", surname="Doe", pin="st1234")
        self.lesson_attendance = LessonAttendance.objects.create(
            staff=self.staff,
            tutor_id=1,
            first_in=timezone.now(),
            latitude=43.207674,
            longitude=76.851377,
        )
        self.task_id = "some-task-id"
        self.api_key = APIKey.objects.create(key_name="Test Key", created_by=self.user)
        self.token = Token.objects.create(user=self.user)

    def test_check_lesson_task_status(self):
        url = reverse("check_lesson_task_status", args=[self.task_id])
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)
        response = self.client.get(url)
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]
        )
        if response.status_code == status.HTTP_200_OK:
            self.assertIn("status", response.data)
        elif response.status_code == status.HTTP_202_ACCEPTED:
            self.assertIn("message", response.data)


class FetcherViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fetcher_user", password="12345")
        self.api_key = APIKey.objects.create(
            key_name="Fetcher Test Key",
            created_by=self.user,
        )
        self.url = reverse("fetcher")
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_success_response_contains_summary_and_duration(
        self, mock_get_all_attendance
    ):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 10,
            "failed_requests": 0,
            "pins_with_events": 8,
            "pins_without_events": 2,
            "created_records": 5,
            "updated_records": 5,
            "event_time_parse_errors": 0,
            "failed_pins": [],
            "errors": [],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Done")
        self.assertIn("duration_seconds", response.data)
        self.assertIn("duration_human_readable", response.data)
        self.assertIn("fetch_summary", response.data)
        self.assertEqual(response.data.get("status"), "success")
        self.assertEqual(response.data["fetch_summary"]["failed_requests"], 0)
        mock_get_all_attendance.assert_awaited_once_with(days=2)

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_partial_errors_returns_207(self, mock_get_all_attendance):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 7,
            "failed_requests": 3,
            "pins_with_events": 6,
            "pins_without_events": 1,
            "created_records": 4,
            "updated_records": 3,
            "event_time_parse_errors": 0,
            "failed_pins": ["T111", "T222", "T333"],
            "errors": [{"pin": "T111", "status": 401}],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(response.data.get("status"), "partial_error")
        self.assertEqual(response.data.get("message"), "Done with errors.")
        self.assertEqual(response.data["fetch_summary"]["failed_requests"], 3)
        self.assertNotIn("errors", response.data["fetch_summary"])
        self.assertIn("error_statuses", response.data["fetch_summary"])

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_all_failed_returns_502(self, mock_get_all_attendance):
        mock_get_all_attendance.return_value = {
            "days": 2,
            "source_date": "2026-02-06",
            "save_date": "2026-02-07",
            "total_pins": 10,
            "successful_requests": 0,
            "failed_requests": 10,
            "pins_with_events": 0,
            "pins_without_events": 0,
            "created_records": 0,
            "updated_records": 0,
            "event_time_parse_errors": 0,
            "failed_pins": ["T111"],
            "errors": [{"pin": "T111", "status": 401}],
        }

        response = self.client.get(self.url, {"days": 2})

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data.get("status"), "failed")
        self.assertEqual(response.data.get("message"), "Fetcher failed.")

    def test_fetcher_invalid_days_returns_400(self):
        response = self.client.get(self.url, {"days": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("monitoring_app.views.cache.add", return_value=False)
    def test_fetcher_returns_429_when_run_is_already_in_progress(self, _mock_cache_add):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data.get("status"), "busy")

    @patch(
        "monitoring_app.views.attendance_fetcher.AsyncAttendanceFetcher.get_all_attendance",
        new_callable=AsyncMock,
    )
    def test_fetcher_response_includes_ambiguous_exit_counters(
        self, mock_get_all_attendance
    ):
        mock_get_all_attendance.return_value = {
            "days": 1,
            "source_date": "2026-03-01",
            "save_date": "2026-03-02",
            "total_pins": 4,
            "successful_requests": 4,
            "failed_requests": 0,
            "pins_with_events": 4,
            "pins_without_events": 0,
            "created_records": 2,
            "updated_records": 2,
            "event_time_parse_errors": 0,
            "ambiguous_exit_candidates": 3,
            "ambiguous_resolved_as_exit": 2,
            "ambiguous_resolved_as_transfer": 1,
            "failed_pins": [],
            "errors": [],
        }

        response = self.client.get(self.url, {"days": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["fetch_summary"]
        self.assertEqual(summary["ambiguous_exit_candidates"], 3)
        self.assertEqual(summary["ambiguous_resolved_as_exit"], 2)
        self.assertEqual(summary["ambiguous_resolved_as_transfer"], 1)


@override_settings(
    ATTENDANCE_EXIT_DEVICE_SNS=frozenset({"QJT3244400440", "CORL223060005"}),
    ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS=frozenset({"QJT3244400440"}),
    ATTENDANCE_REENTRY_DEVICE_SNS=frozenset(
        {"COVS222560013", "CN3R230260010", "CN3R230260002", "CN3R230260003"}
    ),
    ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES=45,
)
class AttendanceFetcherExitResolutionTest(TestCase):
    def _event(self, hh: int, mm: int, dev_sn: str, area: str) -> Dict[str, str]:
        return {
            "eventTime": f"2026-03-01T{hh:02d}:{mm:02d}:00",
            "devSn": dev_sn,
            "areaName": area,
        }

    def _find_item(
        self,
        sequence: Optional[list[Dict[str, str]]],
        dev_sn: str,
        resolution: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        for item in sequence or []:
            if item.get("devSn") != dev_sn:
                continue
            if resolution is None or item.get("exit_resolution") == resolution:
                return item
        return None

    def test_qjt_with_reentry_in_10_minutes_is_bridge_transfer(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 10, "COVS222560013", "Мост из пристройки"),
        ]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)

        qjt_item = self._find_item(area_sequence, "QJT3244400440", "bridge_transfer")
        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as bridge_transfer")
        self.assertEqual(qjt_item.get("exit_candidate"), "1")
        self.assertNotIn("is_exit", qjt_item)
        self.assertEqual(stats["ambiguous_exit_candidates"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_transfer"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 0)

    def test_qjt_without_reentry_in_45_minutes_is_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
        ]
        _, _, effective, area_sequence, intervals, _, _, stats = (
            _compute_attendance_from_events(events)
        )
        qjt_item = self._find_item(area_sequence, "QJT3244400440", "exit")

        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as exit")
        self.assertEqual(qjt_item.get("is_exit"), "1")
        self.assertEqual(effective, 3 * 3600)
        self.assertEqual(len(intervals or []), 1)
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 1)

    def test_qjt_with_reentry_after_50_minutes_is_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 50, "COVS222560013", "Мост из пристройки"),
        ]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)
        qjt_item = self._find_item(area_sequence, "QJT3244400440", "exit")

        self.assertIsNotNone(qjt_item)
        if qjt_item is None:
            self.fail("Expected QJT event resolved as exit")
        self.assertEqual(qjt_item.get("is_exit"), "1")
        self.assertEqual(stats["ambiguous_resolved_as_exit"], 1)
        self.assertEqual(stats["ambiguous_resolved_as_transfer"], 0)

    def test_regular_exit_device_still_works_as_exit(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(18, 0, "CORL223060005", "Выход турникет"),
        ]
        _, _, _, area_sequence, _, _, _, _ = _compute_attendance_from_events(events)
        regular_exit_item = self._find_item(area_sequence, "CORL223060005", "exit")

        self.assertIsNotNone(regular_exit_item)
        if regular_exit_item is None:
            self.fail("Expected regular exit device to be marked as exit")
        self.assertEqual(regular_exit_item.get("is_exit"), "1")
        self.assertEqual(regular_exit_item.get("exit_candidate"), "1")

    def test_first_event_on_exit_device_is_not_exit(self):
        events = [self._event(9, 0, "QJT3244400440", "Переход в пристройку")]
        _, _, _, area_sequence, _, _, _, stats = _compute_attendance_from_events(events)
        first_item = next(iter(area_sequence or []), None)
        if first_item is None:
            self.fail("Expected non-empty area_sequence")
        self.assertNotIn("is_exit", first_item)
        self.assertNotIn("exit_candidate", first_item)
        self.assertEqual(stats["ambiguous_exit_candidates"], 0)

    def test_mixed_intervals_total_seconds_is_merged_correctly(self):
        events = [
            self._event(9, 0, "CN3R230260010", "Главный вход"),
            self._event(12, 0, "QJT3244400440", "Переход в пристройку"),
            self._event(12, 10, "COVS222560013", "Мост из пристройки"),
            self._event(13, 0, "CORL223060005", "Выход турникет"),
            self._event(14, 0, "CN3R230260003", "Главный вход"),
            self._event(18, 0, "QJT3244400440", "Переход в пристройку"),
        ]
        _, _, effective, _, intervals, _, _, _ = _compute_attendance_from_events(events)
        self.assertEqual(effective, 8 * 3600)
        self.assertEqual(len(intervals or []), 2)


_FIXTURE_PHOTO = Path(__file__).resolve().parent / "fixtures" / "test_photo.jpg"
_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c \x24.' \",#\x1c\x1c(7),0144\x1f';=82<.32"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
    b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?"
    b"\x00{\x1f+\x0f\xf0\xff\xd9"
)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    DEBUG=True,
    MEDIA_ROOT=tempfile.gettempdir(),
)
class LessonAttendanceCreateThenPutPhotoTest(APITestCase):
    """
    Интеграционный сценарий "POST создать -> GET task_status -> PUT добавить фото".
    Для теста берём существующие данные БД:
    - первый активный staff-пользователь;
    - первый активный APIKey;
    - Staff с pin=T861T и его фото.
    Запуск одного теста: ...LessonAttendanceCreateThenPutPhotoTest.test_create_then_put_photo_base64
    или ...LessonAttendanceCreateThenPutPhotoTest.test_create_then_put_photo_file
    """

    LAT = 43.26498756460276
    LON = 76.93992733955383

    def setUp(self):
        self.user = (
            User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
        )
        self.assertIsNotNone(self.user, "Нужен активный User с is_staff=True в БД")
        self.api_key = (
            APIKey.objects.filter(is_active=True, created_by=self.user)
            .order_by("id")
            .first()
            or APIKey.objects.filter(is_active=True).order_by("id").first()
        )
        self.assertIsNotNone(self.api_key, "Нужен активный APIKey в БД")
        self.staff = Staff.objects.filter(pin__iexact="T861T").first()
        self.assertIsNotNone(self.staff, "Нужен Staff с pin=T861T в БД")
        if self.staff and self.staff.avatar:
            with self.staff.avatar.open("rb") as f:
                self._photo_bytes = f.read()
        elif _FIXTURE_PHOTO.exists():
            self._photo_bytes = _FIXTURE_PHOTO.read_bytes()
        else:
            self._photo_bytes = _MINIMAL_JPEG
        self.assertTrue(self._photo_bytes, "Не удалось прочитать фото для теста")
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

    def _post_attendance_get_lesson_id(self):
        first_in = timezone.now().isoformat()
        payload = {
            "attendance_data": [
                {
                    "staff_pin": self.staff.pin,
                    "subject_name": "Matrix 101: Красная таблетка",
                    "tutor_id": 101,
                    "tutor": "Морфеус",
                    "first_in": first_in,
                    "latitude": self.LAT,
                    "longitude": self.LON,
                }
            ]
        }
        response = self.client.post(
            reverse("create_lesson_attendance_json"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        task_id = response.data["task_id"]
        task_status_url = reverse(
            "check_lesson_task_status", kwargs={"task_id": task_id}
        )
        for _ in range(10):
            response = self.client.get(task_status_url)
            if (
                response.status_code == status.HTTP_200_OK
                and response.data.get("status") == "Success"
            ):
                break
            if response.status_code == status.HTTP_202_ACCEPTED:
                time.sleep(0.2)
                continue
            self.fail(
                f"Неожиданный ответ check_lesson_task_status: "
                f"{response.status_code} {response.data}"
            )
        else:
            self.fail(f"task_id={task_id} не перешёл в Success за отведённое время")

        lesson_ids = response.data.get("lesson_ids") or []
        self.assertGreaterEqual(len(lesson_ids), 1, response.data)
        self.assertIn("id", lesson_ids[0], response.data)
        return lesson_ids[0]["id"]

    def test_create_then_put_photo_base64(self):
        lesson_id = self._post_attendance_get_lesson_id()
        image_b64 = base64.b64encode(self._photo_bytes).decode("ascii")
        response = self.client.put(
            reverse("update_lesson_attendance", kwargs={"id": lesson_id}),
            {"image": image_b64},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data.get("lesson_id"), lesson_id)
        record = LessonAttendance.objects.get(id=lesson_id)
        self.assertTrue(bool(record.staff_image_path))

    def test_create_then_put_photo_file(self):
        lesson_id = self._post_attendance_get_lesson_id()
        photo_file = SimpleUploadedFile(
            "photo.jpg",
            self._photo_bytes,
            content_type="image/jpeg",
        )
        response = self.client.put(
            reverse("update_lesson_attendance", kwargs={"id": lesson_id}),
            {"image": photo_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data.get("lesson_id"), lesson_id)
        record = LessonAttendance.objects.get(id=lesson_id)
        self.assertTrue(bool(record.staff_image_path))


class TestablePhotoConsumer(PhotoConsumer):
    async def send_batched_events_for_test(self, *, message_type, events):
        await self._send_batched_events(message_type=message_type, events=events)

    def set_update_buffer_for_test(self, buffer_payload):
        self._photo_update_buffer = buffer_payload

    async def flush_photo_updates_for_test(self):
        await self._flush_photo_updates()


class PhotoConsumerProtocolTest(SimpleTestCase):
    def test_batched_events_are_chunked_and_versioned(self):
        consumer = TestablePhotoConsumer()
        consumer.send_json = AsyncMock()
        events = [
            {
                "id": idx + 1,
                "hasPhoto": False,
                "staffPin": f"T{idx + 1:04d}",
                "staffFullName": f"User {idx + 1}",
                "department": "Dept",
                "photoUrl": "",
                "attendanceTime": timezone.now().isoformat(),
                "tutorInfo": "Morpheus (TutorID: 101)",
                "op": "updated",
                "stateCode": "UPDATED_META",
                "versionTs": timezone.now().isoformat(),
            }
            for idx in range(401)
        ]

        async_to_sync(consumer.send_batched_events_for_test)(
            message_type="photos_updated",
            events=events,
        )

        self.assertEqual(consumer.send_json.await_count, 3)
        payloads = [call.args[0] for call in consumer.send_json.await_args_list]
        batch_ids = {payload["batchId"] for payload in payloads}
        self.assertEqual(len(batch_ids), 1)
        self.assertEqual([payload["chunkIndex"] for payload in payloads], [1, 2, 3])
        self.assertTrue(all(payload["totalChunks"] == 3 for payload in payloads))
        self.assertTrue(all(payload["protocol"] == PHOTO_WS_PROTOCOL for payload in payloads))

    def test_deleted_event_is_sent_without_photo_payload(self):
        consumer = TestablePhotoConsumer()
        consumer.send_json = AsyncMock()
        consumer.get_photo_data_bulk = AsyncMock(return_value=[])
        consumer.set_update_buffer_for_test(
            {
                42: {
                    "id": 42,
                    "op": "deleted",
                    "stateCode": STATE_DELETED,
                    "versionTs": timezone.now().isoformat(),
                }
            }
        )

        async_to_sync(consumer.flush_photo_updates_for_test)()

        self.assertEqual(consumer.send_json.await_count, 1)
        payload = consumer.send_json.await_args_list[0].args[0]
        self.assertEqual(payload["type"], "photos_updated")
        self.assertEqual(payload["events"][0]["id"], 42)
        self.assertEqual(payload["events"][0]["stateCode"], STATE_DELETED)
        self.assertEqual(payload["events"][0]["op"], "deleted")
        self.assertEqual(payload["photos"], [])


class LessonAttendanceSignalStateTest(SimpleTestCase):
    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_created_without_image_emits_created_no_photo(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        created_lesson = DummyLesson(lesson_id=1001, staff_image_path=None)
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=created_lesson,
            created=True,
            update_fields=None,
        )
        mock_send_photo_event.assert_called_once_with(
            created_lesson,
            op="created",
            state_code=STATE_CREATED_NO_PHOTO,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_with_image_update_emits_photo_attached(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        updated_lesson = DummyLesson(lesson_id=1002, staff_image_path="/tmp/ws1002.jpg")
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=updated_lesson,
            created=False,
            update_fields={"staff_image_path"},
        )
        mock_send_photo_event.assert_called_once_with(
            updated_lesson,
            op="updated",
            state_code=STATE_PHOTO_ATTACHED,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_deleted_photo_emits_deleted_state(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        deleted_lesson = DummyLesson(lesson_id=1003, staff_image_path="/tmp/ws1003.jpg")
        lesson_signals.send_deleted_photo(
            sender=LessonAttendance,
            instance=deleted_lesson,
        )
        mock_send_photo_event.assert_called_once_with(
            deleted_lesson,
            op="deleted",
            state_code=STATE_DELETED,
        )

    @patch("monitoring_app.signals._invalidate_lesson_staff_cache")
    @patch("monitoring_app.signals._invalidate_lesson_attendance_cache")
    @patch("monitoring_app.signals._send_photo_event")
    def test_send_new_photo_meta_update_without_image_emits_updated_meta(
        self,
        mock_send_photo_event,
        mock_invalidate_attendance_cache,
        mock_invalidate_staff_cache,
    ):
        _ = mock_invalidate_attendance_cache
        _ = mock_invalidate_staff_cache

        class DummyLesson:
            def __init__(self, lesson_id, staff_image_path=None):
                self.id = lesson_id
                self.date_at = timezone.now().date()
                self.staff_image_path = staff_image_path
                self.staff_id = 1

        updated_lesson = DummyLesson(lesson_id=1004, staff_image_path=None)
        lesson_signals.send_new_photo(
            sender=LessonAttendance,
            instance=updated_lesson,
            created=False,
            update_fields={"first_in"},
        )
        mock_send_photo_event.assert_called_once_with(
            updated_lesson,
            op="updated",
            state_code="UPDATED_META",
        )


class DepartmentConfirmationCacheRotationTaskTest(SimpleTestCase):
    @patch("monitoring_app.cache_conf.invalidate_cache_pattern", return_value=17)
    @patch("monitoring_app.cache_conf.Cache.set")
    def test_rotate_department_confirmation_cache_epoch_sets_epoch_and_invalidates(
        self,
        mock_cache_set,
        mock_invalidate_pattern,
    ):
        result = monitoring_tasks.rotate_department_confirmation_cache_epoch()

        self.assertIn("epoch", result)
        self.assertRegex(result["epoch"], r"^\d{10}$")
        self.assertEqual(result["deleted_keys"], 17)
        mock_cache_set.assert_called_once_with(
            monitoring_tasks.DEPARTMENT_CONFIRMATION_EPOCH_CACHE_KEY,
            result["epoch"],
            monitoring_tasks.DEPARTMENT_CONFIRMATION_EPOCH_TTL,
        )
        mock_invalidate_pattern.assert_called_once_with("department_confirmation_*")
