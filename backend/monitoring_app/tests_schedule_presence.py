from datetime import datetime, time, timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from monitoring_app.models import APIKey, ClassLocation, LessonAttendance, Staff, StaffAttendance


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SchedulePresenceTests(APITestCase):
    def setUp(self):
        self.day = timezone.localdate() - timedelta(days=2)
        self.a = ClassLocation.objects.create(
            name="КРМУ", address="Проспект Абылай хана, 51/53", latitude=43.26, longitude=76.94
        )
        self.b = ClassLocation.objects.create(
            name="КРМУ", address="Улица Торекулова, 71", latitude=43.27, longitude=76.93
        )
        self.student = Staff.objects.create(pin="S123S", name="Тест", surname="Студент")
        self.other = Staff.objects.create(pin="S124S", name="Тест", surname="Другой")
        key = APIKey.objects.create(is_active=True, key="schedule-test-key")
        self.client.credentials(HTTP_X_API_KEY=key.key)

    def payload(self, day=None):
        return {
            "date": str(day or self.day),
            "buildings": [
                {"id": self.a.id, "address": self.a.address, "pins": ["S123S", "S124S", "S999S"]},
                {"id": self.b.id, "address": self.b.address, "pins": ["S123S"]},
            ],
        }

    def test_movement_counts_every_visited_building_once_on_event_day(self):
        at = timezone.make_aware(datetime.combine(self.day, time(9)))
        StaffAttendance.objects.create(
            staff=self.student,
            date_at=self.day + timedelta(days=1),
            first_in=at,
            area_name_in="Абылай хана",
            area_name_out="Торекулова",
            area_sequence=[
                {"t": "09:00", "area": "Абылай хана"},
                {"t": "13:00", "area": "Торекулова"},
            ],
        )
        LessonAttendance.objects.create(
            staff=self.student,
            date_at=self.day,
            first_in=at,
            last_out=at + timedelta(hours=1),
            subject_name="Тест",
            tutor_id=1,
            tutor="Тест",
            latitude=self.a.latitude,
            longitude=self.a.longitude,
        )
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 200)
        for row in response.data["results"]:
            self.assertEqual(row["present_pins"], ["S123S"])
        self.assertEqual(response.data["results"][0]["unknown_pins"], ["S999S"])

    def test_id_drift_resolves_by_address_and_far_gps_is_not_presence(self):
        payload = self.payload()
        payload["buildings"][0]["id"] = self.b.id
        payload["buildings"][1]["id"] = self.a.id
        at = timezone.make_aware(datetime.combine(self.day, time(9)))
        LessonAttendance.objects.create(
            staff=self.student,
            date_at=self.day,
            first_in=at,
            last_out=at + timedelta(hours=1),
            subject_name="Тест",
            tutor_id=1,
            tutor="Тест",
            latitude=0,
            longitude=0,
        )
        response = self.client.post("/api/attendance/schedule-presence/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "ok")
        self.assertEqual(response.data["results"][0]["present_pins"], [])

    def test_all_entrance_counts_when_turnstile_report_has_no_entrance(self):
        at = timezone.make_aware(datetime.combine(self.day, time(9)))
        StaffAttendance.objects.create(
            staff=self.student,
            date_at=self.day + timedelta(days=1),
            first_in=None,
            report_variants={
                "all": {"first_in": at.isoformat(), "area_name_in": "Абылай хана"},
                "turnstile": {"first_in": None},
            },
            area_sequence=[{"t": "13:00", "area": "Торекулова"}],
        )
        StaffAttendance.objects.create(
            staff=self.other,
            date_at=self.day + timedelta(days=1),
            first_in=None,
            report_variants={"all": {"first_in": None, "area_name_in": "Абылай хана"}},
            area_sequence=[{"t": "13:00", "area": "Торекулова"}],
        )
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 200)
        for row in response.data["results"]:
            self.assertEqual(row["present_pins"], ["S123S"])

    def test_today_is_rejected_and_api_key_is_required(self):
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(timezone.localdate()), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.client.credentials()
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(), format="json"
        )
        self.assertIn(response.status_code, (401, 403))

    def test_day_without_source_rows_remains_unknown(self):
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "no_data")

    def test_repeated_coordinates_use_index_once_and_query_count_is_constant(self):
        from unittest.mock import patch

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from monitoring_app import utils
        from monitoring_app.services.schedule_presence import schedule_presence

        at = timezone.make_aware(datetime.combine(self.day, time(9)))
        for i in range(20):
            LessonAttendance.objects.create(
                staff=self.student,
                date_at=self.day,
                first_in=at,
                subject_name=f"Занятие {i}",
                tutor_id=1,
                tutor="Тест",
                latitude=self.a.latitude,
                longitude=self.a.longitude,
            )
        with (
            CaptureQueriesContext(connection) as queries,
            patch(
                "monitoring_app.services.schedule_presence.utils.calculate_distance_haversine",
                wraps=utils.calculate_distance_haversine,
            ) as distance,
        ):
            results = schedule_presence(self.day, self.payload()["buildings"])
        self.assertLessEqual(len(queries), 6)
        # Two nearest-neighbor radius checks and one unique point; not 20 × 2.
        self.assertEqual(distance.call_count, 3)
        self.assertEqual(results[0]["present_pins"], ["S123S"])

    def test_eastward_point_in_radius_is_not_lost_by_longitude_scaling(self):
        from math import cos, radians

        at = timezone.make_aware(datetime.combine(self.day, time(9)))
        LessonAttendance.objects.create(
            staff=self.student,
            date_at=self.day,
            first_in=at,
            subject_name="Занятие",
            tutor_id=1,
            tutor="Тест",
            latitude=self.a.latitude,
            longitude=self.a.longitude + 60 / (111195 * cos(radians(self.a.latitude))),
        )
        response = self.client.post(
            "/api/attendance/schedule-presence/", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["present_pins"], ["S123S"])

    def test_spatial_index_preserves_cluster_and_override_radii(self):
        from types import SimpleNamespace

        from monitoring_app import utils
        from monitoring_app.services.schedule_presence import _location_index

        locations = [
            SimpleNamespace(
                id=i, latitude=43.26 + offset, longitude=76.94, acceptance_radius_m=override
            )
            for i, offset, override in [
                (1, 0, None),
                (2, 0, None),
                (3, 0.0001, None),
                (4, 0.001, 125),
            ]
        ]
        _tree, radii = _location_index(locations)
        self.assertEqual(
            radii, utils.compute_class_location_acceptance_radii(locations, r_standalone=70)
        )
        self.assertEqual(radii, {1: 60, 2: 60, 3: 80, 4: 125})
