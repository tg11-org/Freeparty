import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Report(TimeStampedModel):
	class Status(models.TextChoices):
		OPEN = "open", "Open"
		REVIEWING = "reviewing", "Reviewing (Legacy)"
		UNDER_REVIEW = "under_review", "Under Review"
		RESOLVED = "resolved", "Resolved"
		DISMISSED = "dismissed", "Dismissed"
		ACTIONED = "actioned", "Actioned"

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


class SecurityAuditEvent(TimeStampedModel):
	"""
	Security audit trail for sensitive account and moderator actions.
	Enables forensic investigation of account compromises, privilege escalations, etc.
	"""

	class EventType(models.TextChoices):
		LOGIN_SUCCESS = "login_success", "Login Success"
		LOGIN_FAILURE = "login_failure", "Login Failure"
		LOGIN_ANOMALY = "login_anomaly", "Login Anomaly"
		PASSWORD_RESET_REQUEST = "password_reset_request", "Password Reset Request"
		PASSWORD_RESET_COMPLETE = "password_reset_complete", "Password Reset Complete"
		EMAIL_VERIFICATION = "email_verification", "Email Verification"
		EMAIL_CHANGED = "email_changed", "Email Changed"
		MODERATOR_PRIVILEGE_GRANT = "moderator_privilege_grant", "Moderator Privilege Grant"
		MODERATOR_PRIVILEGE_REVOKE = "moderator_privilege_revoke", "Moderator Privilege Revoke"
		MODERATION_ACTION_CREATE = "moderation_action_create", "Moderation Action Created"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="audit_events")
	event_type = models.CharField(max_length=32, choices=EventType.choices)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.TextField(null=True, blank=True)
	details = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["user", "-created_at"]),
			models.Index(fields=["event_type", "-created_at"]),
		]

	def __str__(self):
		return f"{self.event_type} by {self.user.email} at {self.created_at}"


class TrustSignal(TimeStampedModel):
	"""
	Trust/risk indicators for an actor to support abuse detection and adaptive throttling.
	Computed periodically or on-demand; helps staff understand account risk profile.
	"""

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.OneToOneField("actors.Actor", on_delete=models.CASCADE, related_name="trust_signal")

	# Core signals (updated periodically)
	account_age_days = models.IntegerField(default=0)
	email_verified = models.BooleanField(default=False)
	email_verified_at = models.DateTimeField(null=True, blank=True)

	# Moderation signals
	recent_reports_count = models.IntegerField(default=0)  # reports filed against this actor in last 30 days
	recent_actions_count = models.IntegerField(default=0)  # moderation actions taken against this actor in last 30 days

	# Velocity signals
	posts_last_hour = models.IntegerField(default=0)
	follows_last_hour = models.IntegerField(default=0)
	likes_last_hour = models.IntegerField(default=0)
	reposts_last_hour = models.IntegerField(default=0)

	# Computed trust score (0-100 scale; higher = more trustworthy)
	trust_score = models.IntegerField(default=50)

	# Flags
	is_throttled = models.BooleanField(default=False)
	throttle_reason = models.CharField(max_length=64, blank=True)
	throttled_until = models.DateTimeField(null=True, blank=True)

	last_computed_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-last_computed_at"]
		indexes = [
			models.Index(fields=["is_throttled", "-last_computed_at"]),
		]

	def __str__(self):
		return f"TrustSignal: {self.actor.handle} (score={self.trust_score})"


