import uuid
import hashlib

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Report(TimeStampedModel):
	class Reason(models.TextChoices):
		DMCA_IP = "dmca_ip", "DMCA / IP Complaint"
		MINOR_SAFETY = "minor_safety", "Posting of a Minor"
		GRAPHIC_DEATH_INJURY = "graphic_death_injury", "Death or Severe Injury Content"
		NON_CONSENSUAL_INTIMATE_MEDIA = "non_consensual_intimate_media", "Non-Consensual Intimate Media"
		IMPERSONATION = "impersonation", "Impersonation"
		HARASSMENT = "harassment", "Harassment"
		SPAM_SCAM = "spam_scam", "Spam / Scam"
		OTHER = "other", "Other"

	class Severity(models.TextChoices):
		LOW = "low", "Low"
		MEDIUM = "medium", "Medium"
		HIGH = "high", "High"
		CRITICAL = "critical", "Critical"

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
	reason = models.CharField(max_length=128, choices=Reason.choices, default=Reason.OTHER)
	severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
	description = models.TextField(blank=True)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_reports")
	assigned_to = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_reports")
	first_assigned_at = models.DateTimeField(null=True, blank=True)
	responded_at = models.DateTimeField(null=True, blank=True)
	sla_target_minutes = models.PositiveIntegerField(default=0)
	evidence_hash = models.CharField(max_length=64, blank=True)

	@classmethod
	def normalize_reason(cls, reason: str) -> str:
		value = (reason or "").strip().lower()
		legacy_map = {
			"spam": cls.Reason.SPAM_SCAM,
			"scam": cls.Reason.SPAM_SCAM,
			"abuse": cls.Reason.HARASSMENT,
			"user_report": cls.Reason.OTHER,
			"unspecified": cls.Reason.OTHER,
		}
		if value in legacy_map:
			return legacy_map[value]
		valid = {choice for choice, _ in cls.Reason.choices}
		return value if value in valid else cls.Reason.OTHER

	@classmethod
	def severity_for_reason(cls, reason: str) -> str:
		normalized = cls.normalize_reason(reason)
		mapping = {
			cls.Reason.DMCA_IP: cls.Severity.HIGH,
			cls.Reason.MINOR_SAFETY: cls.Severity.CRITICAL,
			cls.Reason.GRAPHIC_DEATH_INJURY: cls.Severity.HIGH,
			cls.Reason.NON_CONSENSUAL_INTIMATE_MEDIA: cls.Severity.CRITICAL,
			cls.Reason.IMPERSONATION: cls.Severity.HIGH,
			cls.Reason.HARASSMENT: cls.Severity.MEDIUM,
			cls.Reason.SPAM_SCAM: cls.Severity.LOW,
			cls.Reason.OTHER: cls.Severity.MEDIUM,
		}
		return mapping[normalized]

	@classmethod
	def sla_target_for_severity(cls, severity: str) -> int:
		mapping = {
			cls.Severity.LOW: 24 * 60,
			cls.Severity.MEDIUM: 8 * 60,
			cls.Severity.HIGH: 2 * 60,
			cls.Severity.CRITICAL: 30,
		}
		return mapping.get(severity, 8 * 60)

	def stamp_evidence_hash(self, *parts: str) -> str:
		joined = "|".join((part or "").strip() for part in parts if (part or "").strip())
		if not joined:
			return self.evidence_hash
		self.evidence_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()
		return self.evidence_hash

	def sla_breached(self) -> bool:
		if not self.sla_target_minutes:
			return False
		if self.responded_at is not None:
			return False
		deadline_anchor = self.first_assigned_at or self.created_at
		if deadline_anchor is None:
			return False
		deadline = deadline_anchor + timezone.timedelta(minutes=self.sla_target_minutes)
		return timezone.now() > deadline

	def save(self, *args, **kwargs):
		self.reason = self.normalize_reason(self.reason)
		self.severity = self.severity_for_reason(self.reason)
		if not self.sla_target_minutes:
			self.sla_target_minutes = self.sla_target_for_severity(self.severity)
		update_fields = kwargs.get("update_fields")
		if update_fields is not None:
			kwargs["update_fields"] = set(update_fields) | {"reason", "severity", "sla_target_minutes"}
		super().save(*args, **kwargs)


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
		ABUSE_AUTO_ACTION = "abuse_auto_action", "Abuse Auto Action"

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


