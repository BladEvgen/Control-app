from typing import cast
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.cache import cache
from django.test import TestCase

from monitoring_app import models, utils


class PasswordResetApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ivan", "ivan@example.com", "Old#Pass1")

    @mock.patch("monitoring_app.utils.send_password_reset_email")
    def test_request_answer_does_not_reveal_account(self, send):
        known = self.client.post("/api/password-reset/", {"identifier": "ivan"})
        unknown = self.client.post("/api/password-reset/", {"identifier": "nobody"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.json(), unknown.json())
        send.assert_called_once()
        self.client.post("/api/password-reset/", {"identifier": "ivan@example.com"})
        send.assert_called_once()

    def test_confirm_sets_password_once(self):
        token = models.PasswordResetToken.generate_token(self.user)
        url = f"/api/password-reset/{token}/"
        self.assertEqual(self.client.get(url).json()["username"], "ivan")
        self.assertEqual(self.client.post(url, {"password": "weak"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"password": "New#Pass1"}).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New#Pass1"))
        self.assertEqual(self.client.post(url, {"password": "Again#Pass2"}).status_code, 410)
        self.assertEqual(self.client.get("/api/password-reset/bogus/").status_code, 410)

    def test_old_links_redirect_to_react(self):
        response = self.client.get("/password-reset/abc/")
        self.assertRedirects(
            response, "/app/password-reset/abc", status_code=301, fetch_redirect_response=False
        )

    def test_reset_email_has_link_in_html_and_text(self):
        self.user.first_name = "<b>Иван</b>"
        self.user.save()
        request = mock.Mock(is_secure=lambda: True, get_host=lambda: "control.example")
        with self.settings(DEFAULT_FROM_EMAIL="noreply@example.com"):
            self.assertTrue(utils.send_password_reset_email(self.user, request))
        message = cast(EmailMultiAlternatives, mail.outbox[0])
        token = models.PasswordResetToken.objects.get(user=self.user).token
        link = f"https://control.example/app/password-reset/{token}"
        html = str(message.alternatives[0][0])
        self.assertIn(link, str(message.body))
        self.assertIn(link, html)
        self.assertIn("&lt;b&gt;Иван&lt;/b&gt;", html)
