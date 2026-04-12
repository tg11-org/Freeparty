import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Report(TimeStampedModel):
	class Status(models.TextChoices):
		OPEN = "open", "Open"
		REVIEWING = "reviewing", "Reviewing"
		RESOLVED = "resolved", "Resolved"
		DISMISSED = "dismissed", "Dismissed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	reporter = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="reports_filed")
	target_actor = models.ForeignKey("actors.Actor", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports_received")
	target_post = models.ForeignKey("posts.Post", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
	reason = models.CharField(max_length=128)
	description = models.TextField(blank=True)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_reports")


class ModerationAction(TimeStampedModel):
	class ActionType(models.TextChoices):
		ACCOUNT_SUSPEND = "account_suspend", "Account Suspend"
		ACCOUNT_LIMIT = "account_limit", "Account Limit"
		POST_HIDE = "post_hide", "Post Hide"
		POST_REMOVE = "post_remove", "Post Remove"
		NOTE = "note", "Internal Note"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	report = models.ForeignKey("moderation.Report", on_delete=models.SET_NULL, null=True, blank=True, related_name="actions")
	actor_target = models.ForeignKey("actors.Actor", on_delete=models.SET_NULL, null=True, blank=True, related_name="moderation_actions")
	post_target = models.ForeignKey("posts.Post", on_delete=models.SET_NULL, null=True, blank=True, related_name="moderation_actions")
	moderator = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="moderation_actions")
	action_type = models.CharField(max_length=32, choices=ActionType.choices)
	notes = models.TextField(blank=True)
	applied_at = models.DateTimeField(auto_now_add=True)


class ModerationNote(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	report = models.ForeignKey("moderation.Report", on_delete=models.CASCADE, related_name="notes")
	author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="moderation_notes")
	body = models.TextField()

