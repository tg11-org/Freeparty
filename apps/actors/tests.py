from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.core.services.uris import post_uri
from apps.posts.models import Post, PostHashtag
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

	def test_verified_badge_and_locked_handle_are_rendered(self):
		self.user.actor.is_verified = True
		self.user.actor.handle_locked = True
		self.user.actor.save(update_fields=["is_verified", "handle_locked", "updated_at"])
		self.client.force_login(self.user)
		response = self.client.get(f"/actors/{self.user.actor.handle}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Verified")
		self.assertContains(response, "locked")


class ActorHashtagSearchTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="hashtag-search@example.com", username="hashtagsearch", password="secret123")
		self.user.mark_email_verified()

	def test_search_by_chained_hashtags(self):
		Post.objects.create(
			author=self.user.actor,
			content="alpha #foo#bar",
			canonical_uri=post_uri("hash-chain"),
		)
		Post.objects.create(
			author=self.user.actor,
			content="alpha #foo only",
			canonical_uri=post_uri("hash-only-foo"),
		)

		response = self.client.get("/actors/search/?q=%23foo%23bar")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "alpha")
		self.assertContains(response, 'href="/actors/search/?q=%23foo"')
		self.assertContains(response, 'href="/actors/search/?q=%23bar"')
		self.assertNotContains(response, "alpha #foo only")
		self.assertNotContains(response, "hash-only-foo")

	def test_search_by_spaced_hashtags(self):
		Post.objects.create(
			author=self.user.actor,
			content="combo #woo #hoo",
			canonical_uri=post_uri("hash-spaced"),
		)
		Post.objects.create(
			author=self.user.actor,
			content="single #woo",
			canonical_uri=post_uri("hash-single"),
		)

		response = self.client.get("/actors/search/?q=%23woo%20%23hoo")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "combo")
		self.assertContains(response, 'href="/actors/search/?q=%23woo"')
		self.assertContains(response, 'href="/actors/search/?q=%23hoo"')
		self.assertNotContains(response, "single")
		self.assertNotContains(response, "hash-single")

	@override_settings(FEATURE_INDEXED_HASHTAG_SEARCH_ENABLED=False)
	def test_search_falls_back_to_regex_when_index_disabled(self):
		post = Post.objects.create(
			author=self.user.actor,
			content="legacy #fallback",
			canonical_uri=post_uri("hash-legacy-fallback"),
		)
		PostHashtag.objects.filter(post=post).delete()

		response = self.client.get("/actors/search/?q=%23fallback")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "legacy")
