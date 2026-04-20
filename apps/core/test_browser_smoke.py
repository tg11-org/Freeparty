import asyncio
import os
from contextlib import contextmanager
from datetime import timedelta
from unittest import SkipTest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import sync_playwright

from apps.accounts.models import User
from apps.profiles.models import ParentalControlChangeRequest, Profile

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@override_settings(
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class BrowserSmokeTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("PLAYWRIGHT_RUN_SMOKE") != "1":
            raise SkipTest("Playwright smoke tests are opt-in. Set PLAYWRIGHT_RUN_SMOKE=1 to run them.")
        super().setUpClass()

    @contextmanager
    def browser_page(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            try:
                yield page
            finally:
                context.close()
                browser.close()

    def test_signup_page_renders_minor_guardian_controls_in_browser(self):
        with self.browser_page() as page:
            page.goto(f"{self.live_server_url}/accounts/signup/")
            page.wait_for_selector('input[name="is_under_18"]', timeout=30000)
            page.wait_for_selector('input[name="guardian_email"]', timeout=30000)
            page.wait_for_selector('input[name="accept_tos"]', timeout=30000)
            page.wait_for_selector('input[name="accept_guidelines"]', timeout=30000)
            page_content = page.content()

        self.assertIn("This account is for someone under 18", page_content)
        self.assertIn("Parent or guardian email", page_content)
        self.assertIn("Terms of Service", page_content)

    def test_guardian_can_reject_change_request_from_review_page(self):
        user = User(email="child@example.com", username="childuser")
        user.set_password("Secretpass123")
        user.save()
        profile = Profile.objects.get(actor__user=user)
        profile.is_minor_account = True
        profile.parental_controls_enabled = True
        profile.guardian_email = "parent@example.com"
        profile.save(
            update_fields=[
                "is_minor_account",
                "parental_controls_enabled",
                "guardian_email",
                "updated_at",
            ]
        )
        change_request = ParentalControlChangeRequest.objects.create(
            profile=profile,
            requested_by=user,
            guardian_email="parent@example.com",
            token="browser-reject-token",
            expires_at=timezone.now() + timedelta(hours=24),
            proposed_is_private_account=True,
            proposed_parental_controls_enabled=True,
            proposed_guardian_email="parent@example.com",
        )

        with self.browser_page() as page:
            page.goto(f"{self.live_server_url}/profiles/guardian/approve/{change_request.token}/")
            self.assertIn("Review requested profile changes", page.content())
            page.click('button[name="action"][value="reject"]')
            page.wait_for_selector("text=has been rejected", timeout=30000)
            rejected_page = page.content()
            page.goto(f"{self.live_server_url}/profiles/guardian/approve/{change_request.token}/")
            expired_page = page.content()

        self.assertIn("has been rejected", rejected_page)
        change_request.refresh_from_db()
        self.assertIsNotNone(change_request.rejected_at)
        self.assertIn("invalid or expired", expired_page)

    def test_home_page_redirects_anonymous_user_to_login(self):
        with self.browser_page() as page:
            page.goto(f"{self.live_server_url}/", wait_until="networkidle")
            final_url = page.url
            page_content = page.content()

        # Anonymous visitors should land somewhere with a login form or prompt.
        has_login = "login" in final_url or "sign" in final_url or "login" in page_content.lower()
        self.assertTrue(has_login, f"Expected login prompt for anonymous user, got URL: {final_url}")

    def test_login_page_has_username_and_password_fields(self):
        with self.browser_page() as page:
            page.goto(f"{self.live_server_url}/accounts/login/")
            page.wait_for_selector('input[name="username"]', timeout=10000)
            page.wait_for_selector('input[name="password"]', timeout=10000)
            page_content = page.content()

        self.assertIn("password", page_content.lower())
