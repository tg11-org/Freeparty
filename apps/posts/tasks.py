from __future__ import annotations

from celery import shared_task

from apps.core.services.task_observability import observe_celery_task
from apps.core.services.task_reliability import (
    mark_task_execution_failed,
    mark_task_execution_succeeded,
    start_task_execution,
)
from apps.posts.models import Attachment


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_media_attachment(
    self,
    attachment_id: str,
    correlation_id: str | None = None,
    idempotency_suffix: str = "default",
) -> None:
    """Process media attachment asynchronously with reliability tracking.

    This is an intentionally narrow first slice for Phase 4.3 that validates media
    metadata and transitions processing state to `processed` or `failed`.
    """

    idempotency_key = f"media_processing:{attachment_id}:{idempotency_suffix}"
    execution, should_skip = start_task_execution(
        task_name=self.name,
        idempotency_key=idempotency_key,
        task_id=getattr(self.request, "id", ""),
        correlation_id=correlation_id,
        payload={"attachment_id": attachment_id},
    )
    if should_skip:
        return

    with observe_celery_task(self, correlation_id=correlation_id):
        try:
            attachment = Attachment.objects.get(id=attachment_id)
            if attachment.processing_state == Attachment.ProcessingState.PROCESSED:
                mark_task_execution_succeeded(execution)
                return

            if attachment.attachment_type not in {
                Attachment.AttachmentType.IMAGE,
                Attachment.AttachmentType.VIDEO,
            }:
                raise ValueError("Unsupported attachment type for media processing")

            if attachment.attachment_type == Attachment.AttachmentType.IMAGE and not attachment.mime_type.startswith("image/"):
                raise ValueError("Attachment metadata mismatch: expected image/* mime type")

            if attachment.attachment_type == Attachment.AttachmentType.VIDEO and not attachment.mime_type.startswith("video/"):
                raise ValueError("Attachment metadata mismatch: expected video/* mime type")

            attachment.processing_state = Attachment.ProcessingState.PROCESSED
            attachment.save(update_fields=["processing_state", "updated_at"])
            mark_task_execution_succeeded(execution)
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            Attachment.objects.filter(id=attachment_id).update(processing_state=Attachment.ProcessingState.FAILED)
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"attachment_id": attachment_id},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            raise