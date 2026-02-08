from datetime import datetime
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from monitoring_app.models import APIKey, LessonAttendance, RemoteWork, Staff
from monitoring_app.views import get_staff_detail

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
    def test_fetcher_success_response_contains_summary_and_duration(self, mock_get_all_attendance):
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
