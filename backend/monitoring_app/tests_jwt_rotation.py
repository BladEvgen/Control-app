"""JWT: ротация отзывает старый refresh, выход отзывает токен, сессия ограничена по времени."""

import time
from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase


class JwtRotationTest(APITestCase):
    def setUp(self):
        cast(Any, get_user_model()).objects.create_user("ivanov", password="Pass-12345!")

    def _login(self):
        response = self.client.post(
            "/api/token/", {"username": "ivanov", "password": "Pass-12345!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["refresh"]

    def _refresh(self, token):
        return self.client.post("/api/token/refresh/", {"refresh": token}, format="json")

    def test_rotated_refresh_cannot_be_replayed(self):
        first = self._login()
        rotated = self._refresh(first)
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(self._refresh(first).status_code, 401)

    def test_logout_revokes_refresh(self):
        token = self._login()
        response = self.client.post("/api/token/blacklist/", {"refresh": token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh(token).status_code, 401)

    @override_settings(JWT_SESSION_MAX_HOURS=12)
    def test_session_cannot_outlive_max_age_by_rotation(self):
        token = self._login()
        thirteen_hours_later = time.time() + 13 * 3600
        with patch("monitoring_app.custom_jwt.time.time", return_value=thirteen_hours_later):
            self.assertEqual(self._refresh(token).status_code, 401)
