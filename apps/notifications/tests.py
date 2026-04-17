from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.posts.models import Post


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class NotificationViewTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="notify@example.com", username="notify", password="secret123")
		self.user.mark_email_verified()
		self.client.force_login(self.user)

	def test_notifications_are_paginated(self):
		for _ in range(26):
			Notification.objects.create(
				recipient=self.user.actor,
				source_actor=self.user.actor,
				notification_type=Notification.NotificationType.SYSTEM,
			)
		response = self.client.get("/notifications/")
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["page_obj"].has_next())
		self.assertEqual(len(response.context["notifications"]), 20)

	def test_notifications_filter_unread(self):
		Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.SYSTEM,
		)
		read_item = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.SYSTEM,
		)
		read_item.read_at = read_item.created_at
		read_item.save(update_fields=["read_at"])
		response = self.client.get("/notifications/?type=unread")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.context["notifications"]), 1)

	def test_mark_single_notification_read(self):
		item = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.SYSTEM,
		)
		self.client.post(f"/notifications/{item.id}/mark-read/")
		item.refresh_from_db()
		self.assertIsNotNone(item.read_at)

	def test_notifications_api_mark_read_and_mark_all(self):
		item1 = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.SYSTEM,
		)
		item2 = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.LIKE,
		)
		response = self.client.post(f"/api/v1/notifications/{item1.id}/mark-read/")
		self.assertEqual(response.status_code, 200)
		response = self.client.post("/api/v1/notifications/mark-all-read/")
		self.assertEqual(response.status_code, 200)
		item1.refresh_from_db()
		item2.refresh_from_db()
		self.assertIsNotNone(item1.read_at)
		self.assertIsNotNone(item2.read_at)

	def test_grouped_notifications_view_mode(self):
		new_item = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.SYSTEM,
		)
		old_item = Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			notification_type=Notification.NotificationType.LIKE,
		)
		Notification.objects.filter(id=old_item.id).update(created_at=timezone.now() - timedelta(days=2))
		response = self.client.get("/notifications/?view=grouped")
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["grouped_view"])
		groups = response.context["grouped_notifications"]
		self.assertGreaterEqual(len(groups), 2)
		flattened = [item.id for group in groups for item in group["items"]]
		self.assertIn(new_item.id, flattened)
		self.assertIn(old_item.id, flattened)

	def test_notifications_render_post_context_summary(self):
		post = Post.objects.create(
			author=self.user.actor,
			canonical_uri="https://example.com/posts/notify-context",
			content="Context post body",
		)
		Notification.objects.create(
			recipient=self.user.actor,
			source_actor=self.user.actor,
			source_post=post,
			notification_type=Notification.NotificationType.REPLY,
			payload={"summary": "Someone replied to your post"},
		)
		response = self.client.get("/notifications/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Someone replied to your post")
		self.assertContains(response, f"/posts/{post.id}/")


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class MentionNotificationTests(TestCase):
	"""Ensure @mention in posts and comments creates MENTION notifications."""

	def setUp(self):
		self.client = Client()
		self.author = User.objects.create_user(email="author@example.com", username="author", password="secret123")
		self.author.mark_email_verified()
		self.mentioned = User.objects.create_user(email="mentioned@example.com", username="mentioned", password="secret123")
		self.mentioned.mark_email_verified()
		self.client.force_login(self.author)

	def test_post_mentioning_user_sends_notification(self):
		response = self.client.post("/posts/new/", {
			"content": "Hello @mentioned, check this out!",
			"visibility": "public",
		})
		self.assertIn(response.status_code, (200, 302))
		self.assertEqual(
			Notification.objects.filter(
				recipient=self.mentioned.actor,
				notification_type=Notification.NotificationType.MENTION,
			).count(),
			1,
		)

	def test_post_self_mention_does_not_send_notification(self):
		self.client.post("/posts/new/", {
			"content": "Hello @author, check this out!",
			"visibility": "public",
		})
		self.assertEqual(
			Notification.objects.filter(
				recipient=self.author.actor,
				notification_type=Notification.NotificationType.MENTION,
			).count(),
			0,
		)

	def test_comment_mentioning_user_sends_notification(self):
		post = Post.objects.create(
			author=self.mentioned.actor,
			canonical_uri="https://example.com/posts/mention-comment-test",
			content="Original post",
		)
		self.client.post(f"/posts/{post.id}/comment/", {"content": "Hey @mentioned nice post!"})
		self.assertEqual(
			Notification.objects.filter(
				recipient=self.mentioned.actor,
				notification_type=Notification.NotificationType.MENTION,
			).count(),
			1,
		)

	def test_comment_on_post_sends_reply_notification_to_author(self):
		third = User.objects.create_user(email="third@example.com", username="third", password="secret123")
		third.mark_email_verified()
		post = Post.objects.create(
			author=third.actor,
			canonical_uri="https://example.com/posts/reply-notif-test",
			content="Post by third",
		)
		self.client.post(f"/posts/{post.id}/comment/", {"content": "Great post!"})
		self.assertEqual(
			Notification.objects.filter(
				recipient=third.actor,
				notification_type=Notification.NotificationType.REPLY,
			).count(),
			1,
		)

	def test_mention_nonexistent_handle_is_ignored(self):
		self.client.post("/posts/new/", {
			"content": "Hello @nobody_exists_xyz!",
			"visibility": "public",
		})
		self.assertEqual(
			Notification.objects.filter(notification_type=Notification.NotificationType.MENTION).count(),
			0,
		)
