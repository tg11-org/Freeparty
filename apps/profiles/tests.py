from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.profiles.models import (
	GuardianEmailVerificationToken,
	GuardianManagementAccessToken,
	ParentalControlChangeRequest,
	ProfileEditHistory,
	ProfileLink,
)


class ProfileEditHistoryTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="profilehist@example.com", username="profilehist", password="secret123")
		self.user.mark_email_verified()

	def test_profile_edit_creates_history(self):
		self.client.force_login(self.user)
		response = self.client.post(
			"/profiles/me/edit/",
			{
				"bio": "Updated bio",
				"location": "Earth",
				"website_url": "https://example.com",
				"show_follower_count": True,
				"show_following_count": True,
				"is_private_account": False,
				"auto_reveal_spoilers": True,
			},
		)
		self.assertEqual(response.status_code, 302)
		history = ProfileEditHistory.objects.filter(profile=self.user.actor.profile).first()
		self.assertIsNotNone(history)
		self.assertEqual(history.new_bio, "Updated bio")
		self.user.actor.profile.refresh_from_db()
		self.assertTrue(self.user.actor.profile.auto_reveal_spoilers)


class ProfileLinksTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="linksuser@example.com", username="linksuser", password="secret123")
		self.user.mark_email_verified()

	def test_owner_can_add_profile_link(self):
		self.client.force_login(self.user)
		response = self.client.post(
			"/profiles/me/links/",
			{
				"title": "Portfolio",
				"url": "https://example.com",
				"display_order": 1,
				"is_active": True,
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(ProfileLink.objects.filter(profile=self.user.actor.profile, title="Portfolio").exists())

	def test_public_links_page_renders_active_links(self):
		ProfileLink.objects.create(
			profile=self.user.actor.profile,
			title="Docs",
			url="https://docs.example.com",
			display_order=1,
			is_active=True,
		)
		ProfileLink.objects.create(
			profile=self.user.actor.profile,
			title="Hidden",
			url="https://hidden.example.com",
			display_order=2,
			is_active=False,
		)
		response = self.client.get(f"/profiles/{self.user.actor.handle}/links/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Docs")
		self.assertNotContains(response, "Hidden")


class ParentalControlsTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="minoruser@example.com", username="minoruser", password="secret123")
		self.user.mark_email_verified()

	def _post_profile(self, **overrides):
		payload = {
			"bio": "",
			"location": "",
			"website_url": "",
			"show_follower_count": True,
			"show_following_count": True,
			"is_private_account": False,
			"auto_reveal_spoilers": False,
			"is_minor_account": False,
			"parental_controls_enabled": False,
			"guardian_email": "",
		}
		payload.update(overrides)
		return self.client.post("/profiles/me/edit/", payload)

	def test_guardian_email_change_sends_verification_email(self):
		self.client.force_login(self.user)
		response = self._post_profile(
			is_minor_account=True,
			parental_controls_enabled=True,
			guardian_email="parent@example.com",
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			GuardianEmailVerificationToken.objects.filter(
				profile=self.user.actor.profile,
				guardian_email="parent@example.com",
			).exists()
		)
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn("guardian", mail.outbox[0].subject.lower())

	def test_guardian_verification_link_marks_profile_verified(self):
		profile = self.user.actor.profile
		profile.guardian_email = "parent@example.com"
		profile.save(update_fields=["guardian_email", "updated_at"])
		token = GuardianEmailVerificationToken.objects.create(
			profile=profile,
			guardian_email="parent@example.com",
			token="verify-token-1",
			expires_at=timezone.now() + timedelta(hours=1),
		)

		response = self.client.get(f"/profiles/guardian/verify/{token.token}/")
		self.assertEqual(response.status_code, 302)
		profile.refresh_from_db()
		token.refresh_from_db()
		self.assertIsNotNone(profile.guardian_email_verified_at)
		self.assertIsNotNone(token.used_at)
		self.assertTrue(GuardianManagementAccessToken.objects.filter(profile=profile).exists())
		self.assertIn("/profiles/guardian/manage/", response.url)

	def test_guardian_management_page_saves_age_and_permissions(self):
		profile = self.user.actor.profile
		profile.is_minor_account = True
		profile.parental_controls_enabled = True
		profile.guardian_email = "parent@example.com"
		profile.guardian_email_verified_at = timezone.now()
		profile.save(
			update_fields=[
				"is_minor_account",
				"parental_controls_enabled",
				"guardian_email",
				"guardian_email_verified_at",
				"updated_at",
			],
		)
		access = GuardianManagementAccessToken.objects.create(
			profile=profile,
			guardian_email="parent@example.com",
			token="guardian-manage-1",
			expires_at=timezone.now() + timedelta(hours=24),
		)

		response = self.client.post(
			f"/profiles/guardian/manage/{access.token}/",
			{
				"minor_birthdate_precision": "month_year",
				"minor_birth_month": 5,
				"minor_birth_year": 2012,
				"guardian_allows_nsfw_underage": "on",
				"guardian_allows_16plus_underage": "on",
				"guardian_locks_account_protection": "on",
				"guardian_restrict_dms_to_teens": "on",
			},
		)
		self.assertEqual(response.status_code, 302)
		profile.refresh_from_db()
		self.assertEqual(profile.minor_birthdate_precision, "month_year")
		self.assertEqual(profile.minor_birth_month, 5)
		self.assertEqual(profile.minor_birth_year, 2012)
		self.assertTrue(profile.guardian_allows_nsfw_underage)
		self.assertTrue(profile.guardian_allows_16plus_underage)
		self.assertTrue(profile.guardian_locks_account_protection)
		self.assertTrue(profile.guardian_restrict_dms_to_teens)

	def test_minor_locked_change_requires_guardian_approval(self):
		self.client.force_login(self.user)
		profile = self.user.actor.profile
		profile.is_minor_account = True
		profile.parental_controls_enabled = True
		profile.guardian_email = "parent@example.com"
		profile.guardian_email_verified_at = timezone.now()
		profile.auto_reveal_spoilers = False
		profile.save(
			update_fields=[
				"is_minor_account",
				"parental_controls_enabled",
				"guardian_email",
				"guardian_email_verified_at",
				"auto_reveal_spoilers",
				"updated_at",
			],
		)

		response = self._post_profile(
			is_minor_account=True,
			parental_controls_enabled=True,
			guardian_email="parent@example.com",
			auto_reveal_spoilers=True,
		)
		self.assertEqual(response.status_code, 302)
		profile.refresh_from_db()
		self.assertFalse(profile.auto_reveal_spoilers)

		change_request = ParentalControlChangeRequest.objects.filter(profile=profile).latest("created_at")
		self.assertEqual(len(mail.outbox), 1)

		approve_response = self.client.get(f"/profiles/guardian/approve/{change_request.token}/")
		self.assertEqual(approve_response.status_code, 302)
		profile.refresh_from_db()
		change_request.refresh_from_db()
		self.assertTrue(profile.auto_reveal_spoilers)
		self.assertIsNotNone(change_request.used_at)

	def test_minor_cannot_disable_parental_lock_without_approval(self):
		self.client.force_login(self.user)
		profile = self.user.actor.profile
		profile.is_minor_account = True
		profile.parental_controls_enabled = True
		profile.guardian_email = "parent@example.com"
		profile.guardian_email_verified_at = timezone.now()
		profile.save(
			update_fields=[
				"is_minor_account",
				"parental_controls_enabled",
				"guardian_email",
				"guardian_email_verified_at",
				"updated_at",
			],
		)

		response = self._post_profile(
			is_minor_account=True,
			parental_controls_enabled=False,
			guardian_email="parent@example.com",
		)
		self.assertEqual(response.status_code, 302)
		profile.refresh_from_db()
		self.assertTrue(profile.parental_controls_enabled)

		change_request = ParentalControlChangeRequest.objects.filter(profile=profile).latest("created_at")
		self.assertFalse(change_request.proposed_parental_controls_enabled)

	def test_guardian_can_lock_basic_profile_and_minor_change_becomes_request(self):
		self.client.force_login(self.user)
		profile = self.user.actor.profile
		profile.is_minor_account = True
		profile.parental_controls_enabled = True
		profile.guardian_email = "parent@example.com"
		profile.guardian_email_verified_at = timezone.now()
		profile.guardian_locks_basic_profile = True
		profile.bio = "Original bio"
		profile.save(
			update_fields=[
				"is_minor_account",
				"parental_controls_enabled",
				"guardian_email",
				"guardian_email_verified_at",
				"guardian_locks_basic_profile",
				"bio",
				"updated_at",
			],
		)

		response = self._post_profile(
			is_minor_account=True,
			parental_controls_enabled=True,
			guardian_email="parent@example.com",
			bio="Requested new bio",
		)
		self.assertEqual(response.status_code, 302)
		profile.refresh_from_db()
		self.assertEqual(profile.bio, "Original bio")

		change_request = ParentalControlChangeRequest.objects.filter(profile=profile).latest("created_at")
		self.assertEqual(change_request.proposed_bio, "Requested new bio")

		approve_response = self.client.get(f"/profiles/guardian/approve/{change_request.token}/")
		self.assertEqual(approve_response.status_code, 302)
		profile.refresh_from_db()
		self.assertEqual(profile.bio, "Requested new bio")


class GuardianLinkedMinorManagementTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.guardian_user = User.objects.create_user(email="guardian@example.com", username="guardian", password="secret123")
		self.guardian_user.mark_email_verified()
		guardian_profile = self.guardian_user.actor.profile
		guardian_profile.is_minor_account = False
		guardian_profile.save(update_fields=["is_minor_account", "updated_at"])

		self.minor_user = User.objects.create_user(email="minorlinked@example.com", username="minorlinked", password="secret123")
		self.minor_user.mark_email_verified()
		minor_profile = self.minor_user.actor.profile
		minor_profile.is_minor_account = True
		minor_profile.parental_controls_enabled = True
		minor_profile.guardian_email = "guardian@example.com"
		minor_profile.guardian_email_verified_at = timezone.now()
		minor_profile.save(
			update_fields=[
				"is_minor_account",
				"parental_controls_enabled",
				"guardian_email",
				"guardian_email_verified_at",
				"updated_at",
			],
		)

	def test_non_minor_guardian_can_view_linked_minor_accounts(self):
		self.client.force_login(self.guardian_user)
		response = self.client.get("/profiles/guardian/minors/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.minor_user.actor.handle)

	def test_non_minor_guardian_can_manage_linked_minor_settings(self):
		self.client.force_login(self.guardian_user)
		minor_profile = self.minor_user.actor.profile
		response = self.client.post(
			f"/profiles/guardian/minors/{minor_profile.id}/",
			{
				"minor_birthdate_precision": "age_range",
				"minor_age_range": "13_15",
				"guardian_locks_basic_profile": "on",
				"guardian_locks_visibility_settings": "on",
				"guardian_locks_account_protection": "on",
			},
		)
		self.assertEqual(response.status_code, 302)
		minor_profile.refresh_from_db()
		self.assertTrue(minor_profile.guardian_locks_basic_profile)
		self.assertTrue(minor_profile.guardian_locks_visibility_settings)
		self.assertTrue(minor_profile.guardian_locks_account_protection)
