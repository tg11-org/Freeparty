import uuid

from django.db import models

from apps.core.models import TimeStampedModel


class Instance(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	domain = models.CharField(max_length=255, unique=True)
	software_name = models.CharField(max_length=100, blank=True)
	software_version = models.CharField(max_length=100, blank=True)
	is_blocked = models.BooleanField(default=False)
	metadata = models.JSONField(default=dict, blank=True)
	last_seen_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["domain"]


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

