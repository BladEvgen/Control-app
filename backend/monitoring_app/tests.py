from datetime import datetime
from typing import Dict, Optional
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from monitoring_app.attendance_fetcher import _compute_attendance_from_events
from monitoring_app.models import APIKey, LessonAttendance, RemoteWork, Staff
from monitoring_app.views import get_staff_detail
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()


# Unit Test for RemoteWorkAdmin
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


# Integration Test for get_staff_detail
class StaffDetailTest(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(name="John", surname="Doe")

    def test_get_staff_detail(self):
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)
        detail = get_staff_detail(self.staff, start_date, end_date)
        self.assertIn("contract_type", detail)
        self.assertIn("salary", detail)


# API Test for check_lesson_task_status
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
        self.assertTrue(area_sequence)
        if not area_sequence:
            self.fail("Expected non-empty area_sequence")
        first_item = area_sequence[0]
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
