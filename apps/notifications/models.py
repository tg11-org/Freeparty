import uuid

from django.db import models


class Notification(models.Model):
	class NotificationType(models.TextChoices):
		FOLLOW = "follow", "Follow"
		LIKE = "like", "Like"
		REPLY = "reply", "Reply"
		MENTION = "mention", "Mention"
		REPOST = "repost", "Repost"
		VERIFICATION = "verification", "Verification"
		MODERATION = "moderation", "Moderation"
		SYSTEM = "system", "System"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	recipient = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="notifications")
	source_actor = models.ForeignKey("actors.Actor", on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_notifications")
	source_post = models.ForeignKey("posts.Post", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
	notification_type = models.CharField(max_length=32, choices=NotificationType.choices)
	payload = models.JSONField(default=dict, blank=True)
	read_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["recipient", "read_at", "created_at"])]

