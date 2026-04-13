import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Post(TimeStampedModel):
	class Visibility(models.TextChoices):
		PUBLIC = "public", "Public"
		UNLISTED = "unlisted", "Unlisted"
		FOLLOWERS_ONLY = "followers_only", "Followers Only"
		PRIVATE = "private", "Private"

	class ModerationState(models.TextChoices):
		NORMAL = "normal", "Normal"
		LIMITED = "limited", "Limited"
		HIDDEN = "hidden", "Hidden"
		TAKEN_DOWN = "taken_down", "Taken Down"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	canonical_uri = models.URLField(max_length=500, unique=True)
	author = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="posts")
	content = models.TextField(max_length=5000)
	spoiler_text = models.CharField(max_length=255, blank=True)
	visibility = models.CharField(max_length=24, choices=Visibility.choices, default=Visibility.PUBLIC)

	in_reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")
	thread_root = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="thread_posts")
	quote_of = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotes")

	local_only = models.BooleanField(default=False)
	federated = models.BooleanField(default=False)
	moderation_state = models.CharField(max_length=24, choices=ModerationState.choices, default=ModerationState.NORMAL)
	deleted_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["author", "created_at"]),
			models.Index(fields=["visibility", "created_at"]),
			models.Index(fields=["deleted_at"]),
		]

	def __str__(self) -> str:
		return f"Post<{self.id}>"

	@property
	def like_count(self) -> int:
		return self.likes.count()

	@property
	def comment_count(self) -> int:
		return self.comments.filter(deleted_at__isnull=True).count()

	@property
	def repost_count(self) -> int:
		return self.reposts.count()


class Comment(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="comments")
	author = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="comments")
	content = models.TextField(max_length=2000)
	deleted_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["created_at"]
		indexes = [
			models.Index(fields=["post", "created_at"]),
		]

	def __str__(self) -> str:
		return f"Comment<{self.id}>"


class Attachment(TimeStampedModel):
	class AttachmentType(models.TextChoices):
		IMAGE = "image", "Image"
		VIDEO = "video", "Video"
		FILE = "file", "File"

	class ProcessingState(models.TextChoices):
		PENDING = "pending", "Pending"
		PROCESSED = "processed", "Processed"
		FAILED = "failed", "Failed"

	class ModerationState(models.TextChoices):
		NORMAL = "normal", "Normal"
		FLAGGED = "flagged", "Flagged"
		REMOVED = "removed", "Removed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="attachments")
	attachment_type = models.CharField(max_length=16, choices=AttachmentType.choices)
	file = models.FileField(upload_to="attachments/%Y/%m/%d")
	alt_text = models.CharField(max_length=500, blank=True)
	mime_type = models.CharField(max_length=255)
	file_size = models.PositiveBigIntegerField(default=0)
	processing_state = models.CharField(max_length=16, choices=ProcessingState.choices, default=ProcessingState.PENDING)
	moderation_state = models.CharField(max_length=16, choices=ModerationState.choices, default=ModerationState.NORMAL)

	class Meta:
		ordering = ["-created_at"]

	class AttachmentType(models.TextChoices):
		IMAGE = "image", "Image"
		VIDEO = "video", "Video"
		FILE = "file", "File"

	class ProcessingState(models.TextChoices):
		PENDING = "pending", "Pending"
		PROCESSED = "processed", "Processed"
		FAILED = "failed", "Failed"

	class ModerationState(models.TextChoices):
		NORMAL = "normal", "Normal"
		FLAGGED = "flagged", "Flagged"
		REMOVED = "removed", "Removed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	post = models.ForeignKey("posts.Post", on_delete=models.CASCADE, related_name="attachments")
	attachment_type = models.CharField(max_length=16, choices=AttachmentType.choices)
	file = models.FileField(upload_to="attachments/%Y/%m/%d")
	alt_text = models.CharField(max_length=500, blank=True)
	mime_type = models.CharField(max_length=255)
	file_size = models.PositiveBigIntegerField(default=0)
	processing_state = models.CharField(max_length=16, choices=ProcessingState.choices, default=ProcessingState.PENDING)
	moderation_state = models.CharField(max_length=16, choices=ModerationState.choices, default=ModerationState.NORMAL)

	class Meta:
		ordering = ["-created_at"]

