"""Verify receiving radii and shared pins through database integrations."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from monitoring_app import models, views
from monitoring_app.admin import ClassLocationAdmin
from monitoring_app.cache_conf import Cache


class GeoReceivingRadiusTests(APITestCase):
    def setUp(self):
        Cache.clear()
        views.CLASS_LOCATION_CACHE["expires_at"] = None
        self.client.force_authenticate(get_user_model().objects.create(username="geo-test"))
        self.near = models.ClassLocation.objects.create(
            name="near",
            address="near",
            latitude=0,
            longitude=0.0002,
            acceptance_radius_m=5,
        )
        self.far = models.ClassLocation.objects.create(
            name="far",
            address="far",
            latitude=0,
            longitude=0.0004,
            acceptance_radius_m=100,
        )
        self.shared = models.ClassLocation.objects.create(
            name="shared",
            address="shared",
            latitude=0,
            longitude=0.0004,
            acceptance_radius_m=100,
        )

    def tearDown(self):
        views.CLASS_LOCATION_CACHE["expires_at"] = None
        Cache.clear()
        super().tearDown()

    def test_locations_returns_farther_accepted_buildings_and_shared_pins(self):
        response = self.client.get(reverse("lesson_locations"), {"latitude": 0, "longitude": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [location["id"] for location in response.data["locations"]],
            [self.far.id, self.shared.id],
        )
        with self.assertNumQueries(0):
            response = self.client.get(reverse("lesson_locations"), {"latitude": 0, "longitude": 0})
        self.assertEqual(response.status_code, 200)

    def test_locations_rejects_nonfinite_coordinates(self):
        for value in ("nan", "inf", "-inf"):
            response = self.client.get(
                reverse("lesson_locations"), {"latitude": value, "longitude": 0}
            )
            self.assertEqual(response.status_code, 400)

    def test_other_worker_refreshes_index_after_location_change(self):
        self.client.get(reverse("lesson_locations"), {"latitude": 0, "longitude": 0})
        old_worker_cache = dict(views.CLASS_LOCATION_CACHE)
        self.far.latitude = 1
        self.far.save(update_fields=["latitude"])
        views.CLASS_LOCATION_CACHE.update(old_worker_cache)
        response = self.client.get(reverse("lesson_locations"), {"latitude": 0, "longitude": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [location["id"] for location in response.data["locations"]], [self.shared.id]
        )

    def test_admin_counts_nearest_accepted_location_only_once(self):
        now = timezone.now()
        staff = models.Staff.objects.create(pin="S900001S", name="Geo", surname="Test")
        models.LessonAttendance.objects.create(
            staff=staff,
            subject_name="Geo",
            tutor_id=1,
            tutor="Tutor",
            first_in=now - timedelta(hours=1),
            last_out=now,
            date_at=timezone.localdate(),
            latitude=0,
            longitude=0,
        )
        model_admin = ClassLocationAdmin(models.ClassLocation, admin.site)
        counts = model_admin._get_location_attendance_period_counts(
            [self.near, self.far, self.shared],
            period_start=now - timedelta(days=1),
            now=now,
            period_label="geo-test",
        )
        self.assertEqual(counts, {self.near.id: 0, self.far.id: 1, self.shared.id: 0})
