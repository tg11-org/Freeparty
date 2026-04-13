from django.test import Client, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.core.services.uris import post_uri
from apps.posts.models import Attachment, Comment, CommentEditHistory, Post, PostEditHistory
from apps.social.models import Block, Follow


class PostTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="poster@example.com", username="poster", password="secret123")
		self.user.mark_email_verified()

	def test_post_creation(self):
		actor = self.user.actor
		post = Post.objects.create(
			author=actor,
			content="Hello world",
			canonical_uri=post_uri("temp"),
		)
		post.canonical_uri = post_uri(post.id)
		post.save(update_fields=["canonical_uri", "updated_at"])
		self.assertEqual(Post.objects.count(), 1)
		self.assertEqual(post.author, actor)

	def test_public_posts_view(self):
		Post.objects.create(
			author=self.user.actor,
			content="Public message",
			canonical_uri=post_uri("public-1"),
		)
		response = Client().get("/posts/public/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Public message")

	def test_create_post_with_image_attachment(self):
		client = Client()
		client.force_login(self.user)
		upload = SimpleUploadedFile("photo.jpg", b"fakejpegdata", content_type="image/jpeg")
		response = client.post(
			"/posts/new/",
			{
				"content": "Photo post",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
				"attachment_alt_text": "A sample photo",
			},
		)
		self.assertEqual(response.status_code, 302)
		post = Post.objects.get(content="Photo post")
		attachment = Attachment.objects.get(post=post)
		self.assertEqual(attachment.attachment_type, Attachment.AttachmentType.IMAGE)
		self.assertEqual(attachment.alt_text, "A sample photo")

	def test_create_post_rejects_non_media_attachment(self):
		client = Client()
		client.force_login(self.user)
		upload = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
		response = client.post(
			"/posts/new/",
			{
				"content": "Bad attachment",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Only image and video uploads are supported.")
		self.assertFalse(Post.objects.filter(content="Bad attachment").exists())


class PostPermissionTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="owner@example.com", username="owner", password="secret123")
		self.viewer = User.objects.create_user(email="viewer@example.com", username="viewer", password="secret123")
		self.owner.mark_email_verified()
		self.viewer.mark_email_verified()

	def _create_post(self, **kwargs):
		defaults = {
			"author": self.owner.actor,
			"content": "Owner content",
			"canonical_uri": post_uri("owner-post"),
		}
		defaults.update(kwargs)
		return Post.objects.create(**defaults)

	def test_non_follower_cannot_view_followers_only_post(self):
		post = self._create_post(visibility=Post.Visibility.FOLLOWERS_ONLY)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers["Location"], "/")

	def test_follower_can_view_followers_only_post(self):
		post = self._create_post(visibility=Post.Visibility.FOLLOWERS_ONLY)
		Follow.objects.create(
			follower=self.viewer.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		self.client.force_login(self.viewer)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Owner content")

	def test_blocked_actor_cannot_view_public_post(self):
		post = self._create_post(visibility=Post.Visibility.PUBLIC)
		Block.objects.create(blocker=self.owner.actor, blocked=self.viewer.actor)
		self.client.force_login(self.viewer)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers["Location"], "/")

	def test_cannot_edit_other_users_post(self):
		post = self._create_post()
		self.client.force_login(self.viewer)
		response = self.client.post(f"/posts/{post.id}/edit/", {"content": "Hacked"})
		post.refresh_from_db()
		self.assertEqual(response.status_code, 302)
		self.assertNotEqual(post.content, "Hacked")

	def test_api_cannot_update_other_users_post(self):
		post = self._create_post()
		self.client.force_login(self.viewer)
		response = self.client.patch(
			f"/api/v1/posts/{post.id}/",
			data='{"content": "api hacked"}',
			content_type="application/json",
		)
		post.refresh_from_db()
		self.assertEqual(response.status_code, 403)
		self.assertNotEqual(post.content, "api hacked")

	def test_public_posts_view_is_paginated(self):
		for i in range(25):
			Post.objects.create(
				author=self.owner.actor,
				content=f"Public message {i}",
				canonical_uri=post_uri(f"public-paginated-{i}"),
			)
		response = self.client.get("/posts/public/")
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["page_obj"].has_next())
		self.assertEqual(len(response.context["posts"]), 20)

	def test_private_account_public_post_hidden_until_follow_accepted(self):
		self.owner.actor.profile.is_private_account = True
		self.owner.actor.profile.save(update_fields=["is_private_account", "updated_at"])
		post = self._create_post(visibility=Post.Visibility.PUBLIC)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 302)
		Follow.objects.create(
			follower=self.viewer.actor,
			followee=self.owner.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		self.client.force_login(self.viewer)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 200)


class CommentApiParityTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.owner = User.objects.create_user(email="comment-owner@example.com", username="commentowner", password="secret123")
		self.other = User.objects.create_user(email="comment-other@example.com", username="commentother", password="secret123")
		self.owner.mark_email_verified()
		self.other.mark_email_verified()
		self.post = Post.objects.create(
			author=self.owner.actor,
			content="Post for comments",
			canonical_uri=post_uri("comment-api-post"),
		)

	def test_comment_api_create_and_owner_update_delete(self):
		self.client.force_login(self.other)
		create = self.client.post(
			"/api/v1/comments/",
			data={"post": str(self.post.id), "content": "First comment"},
		)
		self.assertEqual(create.status_code, 201)
		comment_id = create.json()["id"]
		update = self.client.patch(
			f"/api/v1/comments/{comment_id}/",
			data='{"content": "Edited comment"}',
			content_type="application/json",
		)
		self.assertEqual(update.status_code, 200)
		comment = Comment.objects.get(id=comment_id)
		self.assertTrue(comment.is_edited)
		delete = self.client.delete(f"/api/v1/comments/{comment_id}/")
		self.assertEqual(delete.status_code, 204)

	def test_comment_api_non_owner_cannot_edit_or_delete(self):
		self.client.force_login(self.other)
		create = self.client.post(
			"/api/v1/comments/",
			data={"post": str(self.post.id), "content": "Owner of comment is other"},
		)
		comment_id = create.json()["id"]
		self.client.force_login(self.owner)
		update = self.client.patch(
			f"/api/v1/comments/{comment_id}/",
			data='{"content": "hijack"}',
			content_type="application/json",
		)
		self.assertEqual(update.status_code, 403)
		delete = self.client.delete(f"/api/v1/comments/{comment_id}/")
		self.assertEqual(delete.status_code, 403)


class HomeMediaTabTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="media-tab@example.com", username="mediatab", password="secret123")
		self.source = User.objects.create_user(email="media-source@example.com", username="mediasource", password="secret123")
		self.user.mark_email_verified()
		self.source.mark_email_verified()
		Follow.objects.create(
			follower=self.user.actor,
			followee=self.source.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		self.client.force_login(self.user)

	def test_media_tab_filters_to_image_video_posts(self):
		text_post = Post.objects.create(
			author=self.source.actor,
			content="Text only",
			canonical_uri=post_uri("media-tab-text"),
		)
		media_post = Post.objects.create(
			author=self.source.actor,
			content="Media post",
			canonical_uri=post_uri("media-tab-media"),
		)
		upload = SimpleUploadedFile("clip.mp4", b"fakevideo", content_type="video/mp4")
		Attachment.objects.create(
			post=media_post,
			attachment_type=Attachment.AttachmentType.VIDEO,
			file=upload,
			mime_type="video/mp4",
			file_size=len(b"fakevideo"),
		)

		response = self.client.get("/?tab=media")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Media post")
		self.assertNotContains(response, "Text only")

	def test_public_media_tab_filters_to_image_video_posts(self):
		text_post = Post.objects.create(
			author=self.source.actor,
			content="Public text only",
			canonical_uri=post_uri("public-media-tab-text"),
		)
		media_post = Post.objects.create(
			author=self.source.actor,
			content="Public media post",
			canonical_uri=post_uri("public-media-tab-media"),
		)
		upload = SimpleUploadedFile("image.png", b"fakepng", content_type="image/png")
		Attachment.objects.create(
			post=media_post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)

		response = self.client.get("/posts/public/?tab=media")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Public media post")
		self.assertNotContains(response, "Public text only")


class CommentEditedBadgeTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="comment-edit@example.com", username="commentedit", password="secret123")
		self.user.mark_email_verified()
		self.client.force_login(self.user)
		self.post = Post.objects.create(
			author=self.user.actor,
			content="Post for edited badge",
			canonical_uri=post_uri("comment-edited-badge"),
		)

	def test_only_actually_edited_comment_shows_badge(self):
		fresh = Comment.objects.create(post=self.post, author=self.user.actor, content="Fresh")
		edited = Comment.objects.create(post=self.post, author=self.user.actor, content="Needs edit")

		self.client.post(f"/posts/comments/{edited.id}/edit/", {"content": "Edited now"})
		response = self.client.get(f"/posts/{self.post.id}/")

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "&middot; <span>edited</span>", count=1, html=False)
		fresh.refresh_from_db()
		edited.refresh_from_db()
		self.assertFalse(fresh.is_edited)
		self.assertTrue(edited.is_edited)
		self.assertEqual(CommentEditHistory.objects.filter(comment=edited).count(), 1)


class PostEditHistoryTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="posthist@example.com", username="posthist", password="secret123")
		self.user.mark_email_verified()
		self.post = Post.objects.create(
			author=self.user.actor,
			content="Before",
			canonical_uri=post_uri("post-history"),
		)

	def test_html_post_edit_creates_history_record(self):
		self.client.force_login(self.user)
		response = self.client.post(
			f"/posts/{self.post.id}/edit/",
			{"content": "After", "spoiler_text": "", "visibility": Post.Visibility.PUBLIC, "local_only": False},
		)
		self.assertEqual(response.status_code, 302)
		history = PostEditHistory.objects.filter(post=self.post).first()
		self.assertIsNotNone(history)
		self.assertEqual(history.previous_content, "Before")
		self.assertEqual(history.new_content, "After")
