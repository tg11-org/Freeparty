import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Instance(TimeStampedModel):
	class AllowlistState(models.TextChoices):
		PENDING = "pending", "Pending"
		ALLOWED = "allowed", "Allowed"
		BLOCKED = "blocked", "Blocked"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	domain = models.CharField(max_length=255, unique=True)
	software_name = models.CharField(max_length=100, blank=True)
	software_version = models.CharField(max_length=100, blank=True)
	is_blocked = models.BooleanField(default=False)
	allowlist_state = models.CharField(max_length=16, choices=AllowlistState.choices, default=AllowlistState.PENDING)
	added_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="federation_instances_added")
	allowlist_reason = models.TextField(blank=True)
	metadata = models.JSONField(default=dict, blank=True)
	last_seen_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["domain"]


class RemoteActor(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	instance = models.ForeignKey("federation.Instance", on_delete=models.CASCADE, related_name="remote_actors")
	handle = models.CharField(max_length=255)
	display_name = models.CharField(max_length=255, blank=True)
	canonical_uri = models.URLField(max_length=500, unique=True)
	public_key = models.TextField(blank=True)
	avatar_url = models.URLField(max_length=500, blank=True)
	fetched_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [models.Index(fields=["instance", "handle"])]


class RemotePost(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	instance = models.ForeignKey("federation.Instance", on_delete=models.CASCADE, related_name="remote_posts")
	remote_actor = models.ForeignKey("federation.RemoteActor", on_delete=models.CASCADE, related_name="posts")
	canonical_uri = models.URLField(max_length=500, unique=True)
	content = models.TextField(blank=True)
	attachments = models.JSONField(default=list, blank=True)
	metadata = models.JSONField(default=dict, blank=True)
	fetched_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [models.Index(fields=["instance", "remote_actor", "created_at"])]


class FederationObject(TimeStampedModel):
	class ObjectType(models.TextChoices):
		ACTOR = "actor", "Actor"
		POST = "post", "Post"
		OTHER = "other", "Other"

	class ProcessingState(models.TextChoices):
		NEW = "new", "New"
		PROCESSED = "processed", "Processed"
		FAILED = "failed", "Failed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	instance = models.ForeignKey("federation.Instance", on_delete=models.SET_NULL, null=True, blank=True, related_name="objects")
	canonical_uri = models.URLField(max_length=500, unique=True)
	external_id = models.CharField(max_length=500, unique=True)
	object_type = models.CharField(max_length=16, choices=ObjectType.choices)
	payload = models.JSONField(default=dict, blank=True)
	signature_metadata = models.JSONField(default=dict, blank=True)
	fetched_at = models.DateTimeField(null=True, blank=True)
	processing_state = models.CharField(max_length=16, choices=ProcessingState.choices, default=ProcessingState.NEW)


class FederationDelivery(TimeStampedModel):
	class DeliveryState(models.TextChoices):
		PENDING = "pending", "Pending"
		SUCCESS = "success", "Success"
		RETRYING = "retrying", "Retrying"
		FAILED = "failed", "Failed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	target_instance = models.ForeignKey("federation.Instance", on_delete=models.CASCADE, related_name="deliveries")
	actor = models.ForeignKey("actors.Actor", on_delete=models.SET_NULL, null=True, blank=True, related_name="federation_deliveries")
	object_uri = models.URLField(max_length=500)
	activity_payload = models.JSONField(default=dict)
	state = models.CharField(max_length=16, choices=DeliveryState.choices, default=DeliveryState.PENDING)
	retry_count = models.PositiveIntegerField(default=0)
	last_attempted_at = models.DateTimeField(null=True, blank=True)
	response_code = models.PositiveIntegerField(null=True, blank=True)
	response_body = models.TextField(blank=True)

	class Meta:
		indexes = [models.Index(fields=["state", "retry_count"])]

