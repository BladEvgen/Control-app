from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from monitoring_app.cache_conf import Cache
from monitoring_app.models import APIKey, ChildDepartment, Staff
from monitoring_app.views import (
    get_confirmable_threshold,
    is_main_location_confirmable,
)


class DepartmentAttendanceConfirmationPinsModeTests(APITestCase):
    def setUp(self):
        super().setUp()
        Cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="department_confirmation_user",
            password="test-pass-123",
        )
        self.api_key = APIKey.objects.create(
            key_name="Department Confirmation API Key",
            created_by=self.user,
        )
        self.client.credentials(HTTP_X_API_KEY=self.api_key.key)

        self.url = reverse("department-attendance-confirmation")
        self.department = ChildDepartment.objects.create(
            id="100500",
            name="Резиденты",
        )
        self.staff_a = Staff.objects.create(
            pin="S9614S",
            name="Ainur",
            surname="One",
            department=self.department,
        )
        self.staff_b = Staff.objects.create(
            pin="S30108S",
            name="Ayan",
            surname="Two",
            department=self.department,
        )

    def test_pins_mode_works_with_unknown_department(self):
        response = self.client.get(
            self.url,
            {
                "child_department_id": "unknown-department",
                "date": "2026-03-10",
            },
            HTTP_X_STAFF_PINS="S9614S,S30108S",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["child_department_id"], "unknown-department")
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(set(response.data["by_pin_short"].keys()), {"9614", "30108"})

    def test_legacy_mode_keeps_404_for_unknown_department(self):
        response = self.client.get(
            self.url,
            {
                "child_department_id": "unknown-department",
                "date": "2026-03-10",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pins_mode_cache_is_order_insensitive(self):
        mocked_payload = {
            "date": "2026-03-10",
            "data_available": False,
            "total": 2,
            "locations": [],
            "by_pin_short": {
                "9614": {
                    "confirmed": False,
                    "waiting": True,
                    "location": None,
                    "location_address": None,
                    "first_in": None,
                },
                "30108": {
                    "confirmed": False,
                    "waiting": True,
                    "location": None,
                    "location_address": None,
                    "first_in": None,
                },
            },
        }

        with patch(
            "monitoring_app.views._build_one_day_confirmation",
            return_value=mocked_payload,
        ) as build_mock:
            first = self.client.get(
                self.url,
                {
                    "child_department_id": "unknown-department",
                    "date": "2026-03-10",
                },
                HTTP_X_STAFF_PINS="S9614S,S30108S",
            )
            second = self.client.get(
                self.url,
                {
                    "child_department_id": "unknown-department",
                    "date": "2026-03-10",
                },
                HTTP_X_STAFF_PINS="S30108S,S9614S",
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data, second.data)
        self.assertEqual(build_mock.call_count, 1)

    def test_invalid_staff_pins_header_returns_empty_payload(self):
        response = self.client.get(
            self.url,
            {
                "child_department_id": "unknown-department",
                "date": "2026-03-10",
            },
            HTTP_X_STAFF_PINS="foo,bar,@@@",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 0)
        self.assertEqual(response.data["by_pin_short"], {})


class DepartmentConfirmationSmallGroupsThresholdTests(SimpleTestCase):
    def test_threshold_rules_for_small_groups(self):
        self.assertEqual(get_confirmable_threshold(1), 1)
        self.assertEqual(get_confirmable_threshold(2), 2)
        self.assertEqual(get_confirmable_threshold(3), 2)
        self.assertEqual(get_confirmable_threshold(4), 3)

    def test_two_person_group_requires_both_present_in_main_location(self):
        self.assertFalse(
            is_main_location_confirmable(
                leader_count=1,
                total_group=2,
                total_with_attendance=1,
            )
        )
        self.assertTrue(
            is_main_location_confirmable(
                leader_count=2,
                total_group=2,
                total_with_attendance=2,
            )
        )

    def test_three_person_group_needs_two_in_main_location(self):
        self.assertTrue(
            is_main_location_confirmable(
                leader_count=2,
                total_group=3,
                total_with_attendance=2,
            )
        )
        self.assertFalse(
            is_main_location_confirmable(
                leader_count=1,
                total_group=3,
                total_with_attendance=2,
            )
        )

    def test_four_person_group_requires_three_in_main_location(self):
        self.assertFalse(
            is_main_location_confirmable(
                leader_count=2,
                total_group=4,
                total_with_attendance=2,
            )
        )
        self.assertTrue(
            is_main_location_confirmable(
                leader_count=3,
                total_group=4,
                total_with_attendance=3,
            )
        )
        self.assertFalse(
            is_main_location_confirmable(
                leader_count=2,
                total_group=4,
                total_with_attendance=4,
            )
        )
