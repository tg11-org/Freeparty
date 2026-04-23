from django.test import Client, TestCase, override_settings
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from apps.accounts.models import User
from apps.core.models import AsyncTaskExecution, AsyncTaskFailure
from apps.core.services.uris import post_uri
from apps.moderation.models import Report, TrustSignal
from apps.posts.hashtags import extract_hashtags
from apps.posts.models import Attachment, Comment, CommentEditHistory, Hashtag, LinkPreview, Post, PostEditHistory
from apps.posts.tasks import _fetch_unfurl, _is_ssrf_target, _sanitize_oembed_html, process_media_attachment, unfurl_post_link
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

	def test_create_media_only_post_without_body(self):
		client = Client()
		client.force_login(self.user)
		upload = SimpleUploadedFile("photo.jpg", b"fakejpegdata", content_type="image/jpeg")
		response = client.post(
			"/posts/new/",
			{
				"content": "",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
			},
		)
		self.assertEqual(response.status_code, 302)
		post = Post.objects.order_by("-created_at").first()
		self.assertIsNotNone(post)
		self.assertEqual(post.content, "")

	def test_create_post_rejects_empty_without_body_or_media(self):
		client = Client()
		client.force_login(self.user)
		response = client.post(
			"/posts/new/",
			{
				"content": "   ",
				"visibility": Post.Visibility.PUBLIC,
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Add text or attach media before publishing.")

	def test_create_post_rejects_conflicting_age_gates(self):
		client = Client()
		client.force_login(self.user)
		response = client.post(
			"/posts/new/",
			{
				"content": "Age gated post",
				"visibility": Post.Visibility.PUBLIC,
				"is_16plus": "on",
				"is_18plus": "on",
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Choose either 16+ or 18+ for a post, not both.")
		self.assertFalse(Post.objects.filter(content="Age gated post").exists())

	@override_settings(FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED=True)
	def test_create_post_blocked_for_throttled_actor(self):
		TrustSignal.objects.create(
			actor=self.user.actor,
			is_throttled=True,
			throttle_reason="risk_control",
		)
		client = Client()
		client.force_login(self.user)
		response = client.post(
			"/posts/new/",
			{
				"content": "Should not publish",
				"visibility": Post.Visibility.PUBLIC,
			},
			secure=True,
		)
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Post.objects.filter(content="Should not publish").exists())
		report = Report.objects.filter(target_actor=self.user.actor, reason=Report.Reason.SPAM_SCAM).first()
		self.assertIsNotNone(report)
		self.assertIn("auto:adaptive_abuse", report.description)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
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

	def test_post_detail_renders_rich_og_meta_for_safe_post(self):
		post = self._create_post(content="OG ready post")
		upload = SimpleUploadedFile("image.png", b"fakepng", content_type="image/png")
		Attachment.objects.create(
			post=post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
			moderation_state=Attachment.ModerationState.NORMAL,
		)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'property="og:type" content="article"')
		self.assertContains(response, 'property="og:image"')
		self.assertContains(response, 'name="twitter:image"')

	def test_post_detail_uses_safe_meta_for_nsfw_post(self):
		post = self._create_post(content="Restricted post", is_nsfw=True)
		response = self.client.get(f"/posts/{post.id}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Post on Freeparty (age-restricted content)')
		self.assertNotContains(response, 'property="og:image"')


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


class LinkPreviewTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="preview@example.com", username="previewer", password="secret123")
		self.user.mark_email_verified()
		self.post = Post.objects.create(
			author=self.user.actor,
			content="Watch this https://example.com/demo",
			canonical_uri=post_uri("preview-post"),
		)

	def test_fetch_unfurl_blocks_ssrf_targets(self):
		with patch("urllib.request.urlopen") as mocked_urlopen:
			data = _fetch_unfurl("http://127.0.0.1/internal")
		self.assertEqual(data["fetch_error"], "SSRF blocked")
		mocked_urlopen.assert_not_called()

	def test_fetch_unfurl_blocks_ipv6_private_targets(self):
		self.assertTrue(_is_ssrf_target("http://[::1]/internal"))
		self.assertTrue(_is_ssrf_target("http://[fd00::1]/internal"))

	def test_oembed_html_sanitizer_strips_hostile_iframe_markup(self):
		html = (
			'<iframe src="https://www.youtube.com/embed/demo" onload="alert(1)" '
			'srcdoc="<script>alert(1)</script>" width="560"></iframe><script>alert(2)</script>'
		)
		cleaned = _sanitize_oembed_html(html)
		self.assertIn("<iframe", cleaned)
		self.assertIn("https://www.youtube.com/embed/demo", cleaned)
		self.assertNotIn("onload", cleaned)
		self.assertNotIn("srcdoc", cleaned)
		self.assertNotIn("<script", cleaned)

	def test_oembed_html_sanitizer_rejects_javascript_iframe_src(self):
		cleaned = _sanitize_oembed_html('<iframe src="javascript:alert(1)"></iframe>')
		self.assertEqual(cleaned, "")

	@override_settings(FEATURE_LINK_UNFURL_ENABLED=True)
	@patch("apps.posts.tasks._fetch_unfurl")
	def test_unfurl_task_is_idempotent(self, mocked_fetch_unfurl):
		mocked_fetch_unfurl.return_value = {
			"title": "Example title",
			"description": "Example description",
			"thumbnail_url": "https://cdn.example.com/thumb.png",
			"site_name": "Example",
			"embed_html": "",
		}
		unfurl_post_link.run(str(self.post.id))
		unfurl_post_link.run(str(self.post.id))
		self.assertEqual(LinkPreview.objects.filter(post=self.post).count(), 1)
		mocked_fetch_unfurl.assert_called_once()

	def test_public_timeline_renders_link_preview_card(self):
		LinkPreview.objects.create(
			post=self.post,
			url="https://example.com/demo",
			title="Example preview",
			description="Preview description",
			site_name="Example",
		)
		response = self.client.get("/posts/public/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Example preview")
		self.assertContains(response, "Preview description")


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


class MediaProcessingTaskTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="media-task@example.com", username="mediatask", password="secret123")
		self.user.mark_email_verified()
		self.post = Post.objects.create(
			author=self.user.actor,
			content="Media processing post",
			canonical_uri=post_uri("media-processing-task"),
		)

	def test_media_processing_task_marks_attachment_processed_and_tracks_execution(self):
		upload = SimpleUploadedFile("ok.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)

		process_media_attachment.run(str(attachment.id), correlation_id="corr-1")
		attachment.refresh_from_db()
		self.assertEqual(attachment.processing_state, Attachment.ProcessingState.PROCESSED)
		execution = AsyncTaskExecution.objects.filter(task_name=process_media_attachment.name).first()
		self.assertIsNotNone(execution)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)

	def test_media_processing_task_marks_failed_and_records_failure(self):
		upload = SimpleUploadedFile("bad.bin", b"x", content_type="application/octet-stream")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.FILE,
			file=upload,
			mime_type="application/octet-stream",
			file_size=1,
		)

		with self.assertRaises(Exception):
			process_media_attachment.run(str(attachment.id), correlation_id="corr-2")

		attachment.refresh_from_db()
		self.assertEqual(attachment.processing_state, Attachment.ProcessingState.FAILED)
		failure = AsyncTaskFailure.objects.filter(task_name=process_media_attachment.name).first()
		self.assertIsNotNone(failure)


class MediaProcessingEnqueueTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="media-enqueue@example.com", username="mediaenqueue", password="secret123")
		self.user.mark_email_verified()

	@patch("apps.posts.views.process_media_attachment.delay")
	def test_html_create_post_enqueues_media_processing(self, delay_mock):
		self.client.force_login(self.user)
		upload = SimpleUploadedFile("photo.jpg", b"fakejpegdata", content_type="image/jpeg")
		response = self.client.post(
			"/posts/new/",
			{
				"content": "Photo queue post",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
			},
		)
		self.assertEqual(response.status_code, 302)
		delay_mock.assert_called_once()

	@patch("apps.posts.api_views.process_media_attachment.delay")
	def test_api_create_post_enqueues_media_processing(self, delay_mock):
		self.client.force_login(self.user)
		upload = SimpleUploadedFile("clip.mp4", b"fakevideodata", content_type="video/mp4")
		response = self.client.post(
			"/api/v1/posts/",
			data={
				"content": "API media queue",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
			},
		)
		self.assertEqual(response.status_code, 201)
		delay_mock.assert_called_once()

	def test_api_rejects_empty_post_without_body_or_media(self):
		self.client.force_login(self.user)
		response = self.client.post(
			"/api/v1/posts/",
			data={"content": "   ", "visibility": Post.Visibility.PUBLIC},
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("Add text or attach media before publishing.", str(response.json()))

	@patch("apps.posts.api_views.process_media_attachment.delay")
	def test_api_allows_media_only_post_without_body(self, delay_mock):
		self.client.force_login(self.user)
		upload = SimpleUploadedFile("image.png", b"fakepng", content_type="image/png")
		response = self.client.post(
			"/api/v1/posts/",
			data={
				"content": "",
				"visibility": Post.Visibility.PUBLIC,
				"attachment": upload,
			},
		)
		self.assertEqual(response.status_code, 201)
		delay_mock.assert_called_once()


class ReprocessFailedMediaCommandTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="reprocess@example.com", username="reprocess", password="secret123")
		self.user.mark_email_verified()
		self.post = Post.objects.create(
			author=self.user.actor,
			content="Reprocess post",
			canonical_uri=post_uri("reprocess-failed-media"),
		)

	@patch("apps.posts.management.commands.reprocess_failed_media.process_media_attachment.delay")
	def test_command_requeues_failed_media(self, delay_mock):
		failed_upload = SimpleUploadedFile("failed.mp4", b"abc", content_type="video/mp4")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.VIDEO,
			file=failed_upload,
			mime_type="video/mp4",
			file_size=3,
			processing_state=Attachment.ProcessingState.FAILED,
		)

		call_command("reprocess_failed_media", "--limit", "10")
		attachment.refresh_from_db()
		self.assertEqual(attachment.processing_state, Attachment.ProcessingState.PENDING)
		delay_mock.assert_called_once()


class HashtagIndexingTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="hashtags@example.com", username="hashtags", password="secret123")
		self.user.mark_email_verified()

	def test_extract_hashtags_handles_chained_spaced_and_case(self):
		tags = extract_hashtags("#Foo#bar and #woo #HOO!")
		self.assertEqual(tags, ["foo", "bar", "woo", "hoo"])

	def test_post_save_syncs_hashtags_on_create_and_content_update(self):
		post = Post.objects.create(
			author=self.user.actor,
			content="hello #foo #bar",
			canonical_uri=post_uri("hash-sync"),
		)
		self.assertEqual(set(post.post_hashtags.values_list("hashtag__tag", flat=True)), {"foo", "bar"})

		post.content = "updated #bar #baz"
		post.save(update_fields=["content", "updated_at"])
		self.assertEqual(set(post.post_hashtags.values_list("hashtag__tag", flat=True)), {"bar", "baz"})
		self.assertTrue(Hashtag.objects.filter(tag="foo").exists())


class HashtagBackfillCommandTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="hashbackfill@example.com", username="hashbackfill", password="secret123")
		self.user.mark_email_verified()

	def test_backfill_command_rebuilds_missing_mappings(self):
		post = Post.objects.create(
			author=self.user.actor,
			content="backfill #one #two",
			canonical_uri=post_uri("hash-backfill"),
		)
		post.post_hashtags.all().delete()

		call_command("backfill_hashtags")
		self.assertEqual(set(post.post_hashtags.values_list("hashtag__tag", flat=True)), {"one", "two"})
