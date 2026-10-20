from copy import deepcopy

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from django_settings.admin_theme import PALETTE_COOKIE_NAME


class AdminPaletteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            "palette-admin", "palette@example.com", "test-password"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("monitoring_admin:palette")
        self.index = reverse("monitoring_admin:index")
        self.page = reverse("monitoring_admin:monitoring_app_staff_changelist")

    def test_palette_renders_and_is_private_to_browser(self):
        configured = deepcopy(settings.UNFOLD)
        response = self.client.post(self.url, {"palette": "sky", "next": self.page})
        self.assertRedirects(response, self.page, fetch_redirect_response=False)
        cookie = response.cookies[PALETTE_COOKIE_NAME]
        self.assertEqual(cookie["path"], self.index)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        page = self.client.get(self.page)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, '<select id="admin-palette"')
        self.assertContains(page, 'aria-controls="admin-palette-menu"')
        choices = page.context["admin_palette_choices"]
        self.assertEqual([choice["name"] for choice in choices], list(settings.ADMIN_PALETTES))
        self.assertEqual([choice["name"] for choice in choices if choice["selected"]], ["sky"])
        self.assertTrue(all("--palette-500:oklch(" in choice["style"] for choice in choices))
        self.assertEqual(
            page.context["colors"]["primary"]["500"],
            f"oklch({settings.ADMIN_PALETTES['sky'][5]})",
        )
        other_browser = Client()
        other_browser.force_login(self.user)
        self.assertEqual(
            other_browser.get(self.page).context["admin_palette"], settings.ADMIN_PRIMARY_COLOR
        )
        self.assertEqual(settings.UNFOLD, configured)

    def test_reset_and_unknown_cookie_use_default(self):
        self.client.cookies[PALETTE_COOKIE_NAME] = "unknown"
        self.assertEqual(
            self.client.get(self.page).context["admin_palette"], settings.ADMIN_PRIMARY_COLOR
        )
        self.client.post(self.url, {"palette": "emerald"})
        response = self.client.post(self.url, {"palette": ""})
        self.assertEqual(response.cookies[PALETTE_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(
            self.client.get(self.page).context["admin_palette"], settings.ADMIN_PRIMARY_COLOR
        )

    def test_unknown_palette_is_rejected_and_get_cannot_change_it(self):
        self.assertEqual(self.client.post(self.url, {"palette": "unknown"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"palette": "sky"}).status_code, 405)
        self.assertNotIn(PALETTE_COOKIE_NAME, self.client.cookies)

    def test_requires_admin_access_and_csrf(self):
        anonymous = self.client_class().post(self.url, {"palette": "sky"})
        self.assertEqual(anonymous.status_code, 302)
        self.assertNotIn(PALETTE_COOKIE_NAME, anonymous.cookies)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        self.assertEqual(browser.post(self.url, {"palette": "sky"}).status_code, 403)

    def test_external_redirect_is_rejected_and_https_cookie_is_secure(self):
        response = self.client.post(
            self.url, {"palette": "sky", "next": "https://example.org/"}, secure=True
        )
        self.assertRedirects(response, self.index, fetch_redirect_response=False)
        self.assertTrue(response.cookies[PALETTE_COOKIE_NAME]["secure"])

    def test_choices_follow_settings_without_another_list(self):
        palettes = {**settings.ADMIN_PALETTES, "custom": settings.ADMIN_PALETTES["emerald"]}
        with override_settings(ADMIN_PALETTES=palettes):
            self.client.post(self.url, {"palette": "custom"})
            page = self.client.get(self.page)
            self.assertContains(page, 'value="custom"')
            self.assertContains(page, '<span class="adm-palette-name">Custom</span>', html=True)
            selected = [
                choice for choice in page.context["admin_palette_choices"] if choice["selected"]
            ]
            self.assertEqual([choice["name"] for choice in selected], ["custom"])
            self.assertEqual(page.context["admin_palette"], "custom")
