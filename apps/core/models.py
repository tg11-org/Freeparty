import uuid

from django.db import models


class UUIDPrimaryModel(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

	class Meta:
		abstract = True


class TimeStampedModel(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		abstract = True


class AsyncTaskExecution(TimeStampedModel):
	class Status(models.TextChoices):
		STARTED = "started", "Started"
		SUCCEEDED = "succeeded", "Succeeded"
		FAILED = "failed", "Failed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	task_name = models.CharField(max_length=255)
	idempotency_key = models.CharField(max_length=255)
	task_id = models.CharField(max_length=255, blank=True)
	correlation_id = models.CharField(max_length=255, blank=True)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.STARTED)
	attempt_count = models.PositiveIntegerField(default=1)
	payload = models.JSONField(default=dict, blank=True)
	last_error = models.TextField(blank=True)
	last_traceback = models.TextField(blank=True)
	completed_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["task_name", "idempotency_key"], name="uniq_task_execution_key"),
		]
		indexes = [
			models.Index(fields=["task_name", "status"]),
			models.Index(fields=["correlation_id"]),
		]


class AsyncTaskFailure(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	task_name = models.CharField(max_length=255)
	task_id = models.CharField(max_length=255, blank=True)
	correlation_id = models.CharField(max_length=255, blank=True)
	idempotency_key = models.CharField(max_length=255, blank=True)
	attempt = models.PositiveIntegerField(default=1)
	max_retries = models.PositiveIntegerField(default=0)
	is_terminal = models.BooleanField(default=False)
	terminal_reason = models.CharField(
		max_length=32,
		choices=[
			("max_retries_exceeded", "Max Retries Exceeded"),
			("timeout", "Timeout"),
			("invalid_payload", "Invalid Payload"),
			("manual_dismiss", "Manually Dismissed"),
			("manual_replay", "Manual Replay"),
			("other", "Other"),
		],
		blank=True,
		help_text="Reason why task became terminal (Phase 7.2)",
	)
	error_message = models.TextField()
	traceback = models.TextField(blank=True)
	payload = models.JSONField(default=dict, blank=True)

	class Meta:
		indexes = [
			models.Index(fields=["task_name", "is_terminal"]),
			models.Index(fields=["correlation_id"]),
			models.Index(fields=["is_terminal", "terminal_reason", "created_at"]),
		]

