from django.test import Client, TestCase

from apps.accounts.models import User
from apps.social.models import Follow


class ActorPrivacyVisibilityTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="actor-owner@example.com", username="actorowner", password="secret123")
		self.viewer = User.objects.create_user(email="actor-viewer@example.com", username="actorviewer", password="secret123")
		self.owner.mark_email_verified()
		self.viewer.mark_email_verified()
		self.owner.actor.profile.is_private_account = True
		self.owner.actor.profile.save(update_fields=["is_private_account", "updated_at"])

	def test_private_actor_hidden_from_anonymous(self):
		response = self.client.get(f"/actors/{self.owner.actor.handle}/")
		self.assertEqual(response.status_code, 404)

	def test_private_actor_visible_to_accepted_follower(self):
		Follow.objects.create(
			follower=self.viewer.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		self.client.force_login(self.viewer)
		response = self.client.get(f"/actors/{self.owner.actor.handle}/")
		self.assertEqual(response.status_code, 200)


class ActorDetailSelfControlsTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="self-view@example.com", username="selfview", password="secret123")
		self.user.mark_email_verified()

	def test_self_actor_detail_shows_edit_profile_button(self):
		self.client.force_login(self.user)
		response = self.client.get(f"/actors/{self.user.actor.handle}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Edit profile")
		self.assertContains(response, "/profiles/me/edit/")

	def test_other_actor_detail_hides_edit_profile_button(self):
		other = User.objects.create_user(email="other-view@example.com", username="otherview", password="secret123")
		other.mark_email_verified()
		self.client.force_login(self.user)
		response = self.client.get(f"/actors/{other.actor.handle}/")
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "Edit profile")
