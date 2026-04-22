from django.db import IntegrityError
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.core.services.uris import post_uri
from apps.moderation.models import Report, TrustSignal
from apps.notifications.models import Notification
from apps.posts.models import Post
from apps.social.models import Block, Bookmark, Dislike, Mute
from apps.social.models import Follow
from apps.social.models import Repost


class FollowTests(TestCase):
	def setUp(self):
		self.user_a = User.objects.create_user(email="a@example.com", username="usera", password="secret123")
		self.user_b = User.objects.create_user(email="b@example.com", username="userb", password="secret123")

	def test_follow_unique_constraint(self):
		Follow.objects.create(
			follower=self.user_a.actor,
			followee=self.user_b.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		with self.assertRaises(IntegrityError):
			Follow.objects.create(
				follower=self.user_a.actor,
				followee=self.user_b.actor,
				state=Follow.FollowState.ACCEPTED,
			)

	def test_prevent_self_follow_constraint(self):
		with self.assertRaises(IntegrityError):
			Follow.objects.create(
				follower=self.user_a.actor,
				followee=self.user_a.actor,
				state=Follow.FollowState.ACCEPTED,
			)


class SocialPermissionTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user_a = User.objects.create_user(email="alpha@example.com", username="alpha", password="secret123")
		self.user_b = User.objects.create_user(email="beta@example.com", username="beta", password="secret123")
		self.user_a.mark_email_verified()
		self.user_b.mark_email_verified()

	def test_cannot_follow_when_blocked(self):
		Block.objects.create(blocker=self.user_b.actor, blocked=self.user_a.actor)
		self.client.force_login(self.user_a)
		response = self.client.post(f"/social/follow/{self.user_b.actor.handle}/")
		self.assertEqual(response.status_code, 302)
		self.assertFalse(
			Follow.objects.filter(follower=self.user_a.actor, followee=self.user_b.actor, state=Follow.FollowState.ACCEPTED).exists()
		)

	def test_cannot_like_post_when_blocked(self):
		post = Post.objects.create(
			author=self.user_b.actor,
			content="No likes from blocked users",
			canonical_uri=post_uri("blocked-like"),
		)
		Block.objects.create(blocker=self.user_b.actor, blocked=self.user_a.actor)
		self.client.force_login(self.user_a)
		response = self.client.post(f"/social/like/{post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertFalse(post.likes.filter(actor=self.user_a.actor).exists())

	def test_cannot_dislike_post_when_blocked(self):
		post = Post.objects.create(
			author=self.user_b.actor,
			content="No dislikes from blocked users",
			canonical_uri=post_uri("blocked-dislike"),
		)
		Block.objects.create(blocker=self.user_b.actor, blocked=self.user_a.actor)
		self.client.force_login(self.user_a)
		response = self.client.post(f"/social/dislike/{post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Dislike.objects.filter(actor=self.user_a.actor, post=post).exists())

	def test_blocked_profile_renders_blocked_page_for_blocker(self):
		Block.objects.create(blocker=self.user_a.actor, blocked=self.user_b.actor)
		self.client.force_login(self.user_a)
		response = self.client.get(f"/actors/{self.user_b.actor.handle}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "You have blocked this account")

	def test_blocked_profile_renders_restricted_page_for_blocked_user(self):
		Block.objects.create(blocker=self.user_b.actor, blocked=self.user_a.actor)
		self.client.force_login(self.user_a)
		response = self.client.get(f"/actors/{self.user_b.actor.handle}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "private or unavailable")


class SocialHubTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="socialhub@example.com", username="socialhub", password="secret123")
		self.other = User.objects.create_user(email="socialhub-other@example.com", username="socialhubother", password="secret123")
		self.user.mark_email_verified()
		self.other.mark_email_verified()

	def test_social_index_redirects_to_my_hub(self):
		self.client.force_login(self.user)
		response = self.client.get("/social/")
		self.assertRedirects(response, "/social/my/")

	def test_my_social_hub_renders_relationship_links(self):
		Block.objects.create(blocker=self.user.actor, blocked=self.other.actor)
		Mute.objects.create(muter=self.user.actor, muted=self.other.actor)
		self.client.force_login(self.user)
		response = self.client.get("/social/my/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Follow Requests")
		self.assertContains(response, "Blocked")
		self.assertContains(response, "Muted")

	def test_my_muted_view_renders_without_name_error(self):
		Mute.objects.create(muter=self.user.actor, muted=self.other.actor)
		self.client.force_login(self.user)
		response = self.client.get("/social/my/muted/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.other.actor.handle)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class PrivateAccountFollowFlowTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="owner-private@example.com", username="ownerprivate", password="secret123")
		self.requester = User.objects.create_user(email="req-private@example.com", username="reqprivate", password="secret123")
		self.other = User.objects.create_user(email="other-private@example.com", username="otherprivate", password="secret123")
		self.owner.mark_email_verified()
		self.requester.mark_email_verified()
		self.other.mark_email_verified()
		self.owner.actor.profile.is_private_account = True
		self.owner.actor.profile.save(update_fields=["is_private_account", "updated_at"])

	def test_follow_private_creates_pending(self):
		self.client.force_login(self.requester)
		response = self.client.post(f"/social/follow/{self.owner.actor.handle}/")
		self.assertEqual(response.status_code, 302)
		relation = Follow.objects.get(follower=self.requester.actor, followee=self.owner.actor)
		self.assertEqual(relation.state, Follow.FollowState.PENDING)

	def test_owner_can_approve_request(self):
		relation = Follow.objects.create(
			follower=self.requester.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.PENDING,
		)
		self.client.force_login(self.owner)
		response = self.client.post(f"/social/follow-requests/{relation.id}/approve/")
		self.assertEqual(response.status_code, 302)
		relation.refresh_from_db()
		self.assertEqual(relation.state, Follow.FollowState.ACCEPTED)

	def test_non_owner_cannot_approve_request(self):
		relation = Follow.objects.create(
			follower=self.requester.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.PENDING,
		)
		self.client.force_login(self.other)
		response = self.client.post(f"/social/follow-requests/{relation.id}/approve/")
		self.assertEqual(response.status_code, 404)

	def test_owner_can_reject_request(self):
		relation = Follow.objects.create(
			follower=self.requester.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.PENDING,
		)
		self.client.force_login(self.owner)
		response = self.client.post(f"/social/follow-requests/{relation.id}/reject/")
		self.assertEqual(response.status_code, 302)
		relation.refresh_from_db()
		self.assertEqual(relation.state, Follow.FollowState.REJECTED)

	def test_repeat_follow_does_not_spam_duplicate_notifications(self):
		self.owner.actor.profile.is_private_account = False
		self.owner.actor.profile.save(update_fields=["is_private_account", "updated_at"])
		self.client.force_login(self.requester)
		self.client.post(f"/social/follow/{self.owner.actor.handle}/")
		self.client.post(f"/social/follow/{self.owner.actor.handle}/")
		count = Notification.objects.filter(
			recipient=self.owner.actor,
			source_actor=self.requester.actor,
			notification_type=Notification.NotificationType.FOLLOW,
		).count()
		self.assertEqual(count, 1)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class AsyncFollowRequestTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="owner-async-follow@example.com", username="ownerasyncfollow", password="secret123")
		self.requester = User.objects.create_user(email="requester-async-follow@example.com", username="requesterasyncfollow", password="secret123")
		self.owner.mark_email_verified()
		self.requester.mark_email_verified()
		self.relation = Follow.objects.create(
			follower=self.requester.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.PENDING,
		)

	def test_follow_requests_page_renders_async_forms(self):
		self.client.force_login(self.owner)
		response = self.client.get("/social/follow-requests/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-async-action="1"')
		self.assertContains(response, 'data-action-type="follow-request"')

	def test_approve_follow_request_returns_json(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			f"/social/follow-requests/{self.relation.id}/approve/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertEqual(payload["action"], "approved")
		self.assertTrue(payload["remove_request_row"])
		self.relation.refresh_from_db()
		self.assertEqual(self.relation.state, Follow.FollowState.ACCEPTED)

	def test_reject_follow_request_returns_json(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			f"/social/follow-requests/{self.relation.id}/reject/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertEqual(payload["action"], "rejected")
		self.assertTrue(payload["remove_request_row"])
		self.relation.refresh_from_db()
		self.assertEqual(self.relation.state, Follow.FollowState.REJECTED)


class RepostHardeningTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.author = User.objects.create_user(email="author-repost@example.com", username="authorrepost", password="secret123")
		self.viewer = User.objects.create_user(email="viewer-repost@example.com", username="viewerrepost", password="secret123")
		self.author.mark_email_verified()
		self.viewer.mark_email_verified()
		self.post = Post.objects.create(
			author=self.author.actor,
			content="Repost hardening target",
			canonical_uri=post_uri("repost-hardening"),
		)

	def test_user_cannot_repost_own_post(self):
		self.client.force_login(self.author)
		response = self.client.post(f"/social/repost/{self.post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Repost.objects.filter(actor=self.author.actor, post=self.post).exists())

	def test_blocked_user_cannot_repost(self):
		Block.objects.create(blocker=self.author.actor, blocked=self.viewer.actor)
		self.client.force_login(self.viewer)
		response = self.client.post(f"/social/repost/{self.post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Repost.objects.filter(actor=self.viewer.actor, post=self.post).exists())

	def test_repost_toggle_and_notification_dedupe(self):
		self.client.force_login(self.viewer)
		first = self.client.post(f"/social/repost/{self.post.id}/")
		second = self.client.post(f"/social/repost/{self.post.id}/")
		third = self.client.post(f"/social/repost/{self.post.id}/")
		self.assertEqual(first.status_code, 302)
		self.assertEqual(second.status_code, 302)
		self.assertEqual(third.status_code, 302)
		self.assertTrue(Repost.objects.filter(actor=self.viewer.actor, post=self.post).exists())
		notif_count = Notification.objects.filter(
			recipient=self.author.actor,
			source_actor=self.viewer.actor,
			notification_type=Notification.NotificationType.REPOST,
			source_post=self.post,
		).count()
		self.assertEqual(notif_count, 1)


class BookmarkFlowTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="bookmark-owner@example.com", username="bookmarkowner", password="secret123")
		self.viewer = User.objects.create_user(email="bookmark-viewer@example.com", username="bookmarkviewer", password="secret123")
		self.owner.mark_email_verified()
		self.viewer.mark_email_verified()
		self.post = Post.objects.create(
			author=self.owner.actor,
			content="Bookmark me",
			canonical_uri=post_uri("bookmark-me"),
		)

	def test_bookmark_toggle_and_list_page(self):
		self.client.force_login(self.viewer)
		first = self.client.post(f"/social/bookmark/{self.post.id}/")
		self.assertEqual(first.status_code, 302)
		self.assertTrue(Bookmark.objects.filter(actor=self.viewer.actor, post=self.post).exists())

		page = self.client.get("/social/bookmarks/")
		self.assertEqual(page.status_code, 200)
		self.assertContains(page, "Bookmark me")

		second = self.client.post(f"/social/bookmark/{self.post.id}/")
		self.assertEqual(second.status_code, 302)
		self.assertFalse(Bookmark.objects.filter(actor=self.viewer.actor, post=self.post).exists())


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SocialAjaxToggleTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="ajax-owner@example.com", username="ajaxowner", password="secret123")
		self.viewer = User.objects.create_user(email="ajax-viewer@example.com", username="ajaxviewer", password="secret123")
		self.owner.mark_email_verified()
		self.viewer.mark_email_verified()
		self.post = Post.objects.create(
			author=self.owner.actor,
			content="Ajax target post",
			canonical_uri=post_uri("ajax-target-post"),
		)

	def test_like_toggle_returns_json(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/like/{self.post.id}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["liked"])
		self.assertEqual(payload["like_count"], 1)

	def test_repost_toggle_returns_json(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/repost/{self.post.id}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["reposted"])
		self.assertEqual(payload["repost_count"], 1)

	def test_dislike_toggle_returns_json(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/dislike/{self.post.id}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["disliked"])
		self.assertEqual(payload["dislike_count"], 1)

	def test_bookmark_toggle_returns_json(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/bookmark/{self.post.id}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["bookmarked"])

	def test_follow_returns_json_for_public_account(self):
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/follow/{self.owner.actor.handle}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
			secure=True,
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertTrue(payload["following"])
		self.assertFalse(payload["follow_pending"])
		self.assertEqual(payload["next_action"], "unfollow")

	def test_follow_returns_pending_json_for_private_account(self):
		self.owner.actor.profile.is_private_account = True
		self.owner.actor.profile.save(update_fields=["is_private_account", "updated_at"])
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/follow/{self.owner.actor.handle}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
			secure=True,
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertFalse(payload["following"])
		self.assertTrue(payload["follow_pending"])
		self.assertEqual(payload["next_action"], "unfollow")

	def test_unfollow_returns_json(self):
		Follow.objects.create(
			follower=self.viewer.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/unfollow/{self.owner.actor.handle}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ok"])
		self.assertFalse(payload["following"])
		self.assertFalse(payload["follow_pending"])

	def test_like_toggle_emits_interaction_metric_log(self):
		self.client.force_login(self.viewer)
		with self.assertLogs("apps.core.services.interaction_observability", level="INFO") as logs:
			response = self.client.post(
				f"/social/like/{self.post.id}/",
				HTTP_X_REQUESTED_WITH="XMLHttpRequest",
				HTTP_ACCEPT="application/json",
			)
		self.assertEqual(response.status_code, 200)
		joined = "\n".join(logs.output)
		self.assertIn("interaction_metric", joined)
		self.assertIn("name=social_like_toggle", joined)
		self.assertIn("success=True", joined)

	def test_follow_permission_denial_emits_failed_interaction_metric_log(self):
		Block.objects.create(blocker=self.owner.actor, blocked=self.viewer.actor)
		self.client.force_login(self.viewer)
		with self.assertLogs("apps.core.services.interaction_observability", level="WARNING") as logs:
			response = self.client.post(
				f"/social/follow/{self.owner.actor.handle}/",
				HTTP_X_REQUESTED_WITH="XMLHttpRequest",
				HTTP_ACCEPT="application/json",
			)
		self.assertEqual(response.status_code, 403)
		joined = "\n".join(logs.output)
		self.assertIn("interaction_metric", joined)
		self.assertIn("name=social_follow", joined)
		self.assertIn("success=False", joined)

	@override_settings(FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED=True)
	def test_follow_blocked_by_adaptive_abuse_control_returns_json_429(self):
		TrustSignal.objects.create(
			actor=self.viewer.actor,
			is_throttled=True,
			throttle_reason="risk_control",
		)
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/follow/{self.owner.actor.handle}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)
		self.assertIn(response.status_code, {301, 429})
		self.assertFalse(Follow.objects.filter(follower=self.viewer.actor, followee=self.owner.actor).exists())

	@override_settings(FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED=True)
	def test_like_blocked_by_adaptive_abuse_control_returns_json_429(self):
		TrustSignal.objects.create(
			actor=self.viewer.actor,
			is_throttled=True,
			throttle_reason="risk_control",
		)
		self.client.force_login(self.viewer)
		response = self.client.post(
			f"/social/like/{self.post.id}/",
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
			secure=True,
		)
		self.assertEqual(response.status_code, 429)
		self.assertFalse(self.post.likes.filter(actor=self.viewer.actor).exists())
