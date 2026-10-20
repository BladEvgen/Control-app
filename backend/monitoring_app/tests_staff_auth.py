"""Вход сотрудника по PIN + лицу и отправка «работает» по staff-JWT."""

import time
from datetime import date, timedelta
from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from monitoring_app.models import RemoteActivityDay, Staff

FACE_OK = Response({"matched": True, "final_decision": "verified", "max_cosine": 0.78})
FACE_REPLAY = Response({"matched": True, "final_decision": "verified", "max_cosine": 1.0})
FACE_NO = Response({"matched": False, "final_decision": "rejected"})


class StaffAuthTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.staff = Staff.objects.create(pin="T0005T", name="И. И.", surname="Иванов")

    def _login(self, face=FACE_OK, pin="T0005T"):
        image = SimpleUploadedFile("face.jpg", b"jpeg-bytes", content_type="image/jpeg")
        with patch("monitoring_app.views.verify_staff_face", return_value=face):
            return self.client.post("/api/staff-auth/login/", {"pin": pin, "image": image})

    def _bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_face_match_issues_tokens_and_mismatch_does_not(self):
        self.assertEqual(self._login(face=FACE_NO).status_code, 401)
        self.assertEqual(self._login(face=FACE_REPLAY).status_code, 401)
        self.assertEqual(self._login(pin="NOPE").status_code, 401)
        ok = self._login()
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["access_expires_in"], 15 * 60)

    def test_staff_token_reports_own_work_only_where_allowed(self):
        access = self._login().json()["access"]

        response = self.client.post(
            "/api/activity/",
            {"start": "2026-03-15T23:30:00+05:00", "end": "2026-03-16T00:30:00+05:00"},
            format="json",
            headers=self._bearer(access),
        )

        self.assertEqual(response.status_code, 204)
        rows = dict(
            RemoteActivityDay.objects.filter(staff=self.staff).values_list("day", "active_seconds")
        )
        self.assertEqual(rows, {date(2026, 3, 15): 1800, date(2026, 3, 16): 1800})
        admin_api = "/api/department/stats/X/?start_date=2026-03-01&end_date=2026-03-02"
        self.assertEqual(self.client.get(admin_api, headers=self._bearer(access)).status_code, 403)

    def test_admin_jwt_and_api_key_cannot_report_activity(self):
        user = cast(Any, get_user_model()).objects.create_user("admin2", password="x-12345!")
        admin_access = str(AccessToken.for_user(user))
        response = self.client.post("/api/activity/", {}, headers=self._bearer(admin_access))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.client.post("/api/activity/", {}, headers={"X-API-KEY": "any"}).status_code, 401
        )

    def test_refresh_is_single_use_and_session_has_a_ceiling(self):
        refresh = self._login().json()["refresh"]
        rotated = self.client.post("/api/staff-auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(rotated.status_code, 200)
        replay = self.client.post("/api/staff-auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(replay.status_code, 401)

        later = time.time() + 11 * 3600
        with patch("monitoring_app.views.time.time", return_value=later):
            expired = self.client.post(
                "/api/staff-auth/refresh/", {"refresh": rotated.json()["refresh"]}, format="json"
            )
        self.assertEqual(expired.status_code, 401)

    def test_logout_revokes_and_archived_staff_is_locked_out(self):
        tokens = self._login().json()
        self.client.post("/api/staff-auth/logout/", {"refresh": tokens["refresh"]}, format="json")
        refreshed = self.client.post(
            "/api/staff-auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 401)

        self.staff.archived_at = timezone.now() - timedelta(minutes=1)
        self.staff.save(update_fields=["archived_at"])
        response = self.client.post("/api/activity/", {}, headers=self._bearer(tokens["access"]))
        self.assertEqual(response.status_code, 401)

    def test_login_attempts_per_pin_are_limited(self):
        codes = [self._login(face=FACE_NO).status_code for _ in range(6)]
        self.assertEqual(codes[-1], 429)

    def test_swagger_documents_staff_auth(self):
        admin = cast(Any, get_user_model()).objects.create_superuser("sw", "s@e.com", "x-12345!")
        self.client.force_login(admin)
        paths = self.client.get("/swagger.json").json()["paths"]
        self.assertTrue({"/api/staff-auth/login/", "/api/activity/"} <= set(paths))

    def test_issue_command_gives_working_pair_by_pin(self):
        import io
        import json

        from django.core.management import call_command

        out = io.StringIO()
        call_command("issue_staff_tokens", pin="t0005t", stdout=out)
        access = json.loads(out.getvalue())["access"]
        response = self.client.post("/api/activity/", {}, headers=self._bearer(access))
        self.assertEqual(response.status_code, 204)
