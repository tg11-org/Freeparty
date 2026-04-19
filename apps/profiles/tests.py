from django.test import Client, TestCase

from apps.accounts.models import User
from apps.profiles.models import ProfileEditHistory, ProfileLink


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
