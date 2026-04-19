import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Actor(TimeStampedModel):
	class ActorType(models.TextChoices):
		LOCAL = "local", "Local"
		REMOTE = "remote", "Remote"

	class ActorState(models.TextChoices):
		ACTIVE = "active", "Active"
		SUSPENDED = "suspended", "Suspended"
		DELETED = "deleted", "Deleted"
		REMOTE = "remote", "Remote"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="actor", null=True, blank=True)

	actor_type = models.CharField(max_length=16, choices=ActorType.choices, default=ActorType.LOCAL)
	state = models.CharField(max_length=16, choices=ActorState.choices, default=ActorState.ACTIVE)

	handle = models.CharField(max_length=128, unique=True)
	canonical_uri = models.URLField(max_length=500, unique=True)
	local_username = models.CharField(max_length=30, blank=True)
	is_verified = models.BooleanField(default=False)
	verified_at = models.DateTimeField(null=True, blank=True)
	verified_label = models.CharField(max_length=80, blank=True)
	handle_locked = models.BooleanField(default=False)

	remote_domain = models.CharField(max_length=255, blank=True)
	inbox_url = models.URLField(max_length=500, blank=True)
	outbox_url = models.URLField(max_length=500, blank=True)
	shared_inbox_url = models.URLField(max_length=500, blank=True)
	remote_document = models.JSONField(default=dict, blank=True)
	fetched_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["actor_type", "state"]),
			models.Index(fields=["remote_domain"]),
			models.Index(fields=["is_verified", "handle_locked"]),
		]

	def __str__(self) -> str:
		return self.handle

