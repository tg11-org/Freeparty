from celery import shared_task

from apps.core.services.task_observability import observe_celery_task
from apps.core.services.task_reliability import (
    mark_task_execution_failed,
    mark_task_execution_succeeded,
    start_task_execution,
)
from apps.notifications.models import Notification


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_notification_fanout(self, notification_id: str, correlation_id: str | None = None) -> None:
    idempotency_key = f"notification_fanout:{notification_id}"
    execution, should_skip = start_task_execution(
        task_name=self.name,
        idempotency_key=idempotency_key,
        task_id=getattr(self.request, "id", ""),
        correlation_id=correlation_id,
        payload={"notification_id": notification_id},
    )
    if should_skip:
        return

    with observe_celery_task(self, correlation_id=correlation_id):
        try:
            # Placeholder for future fanout-on-write and websocket publish.
            Notification.objects.filter(id=notification_id).exists()
            mark_task_execution_succeeded(execution)
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                terminal_reason="max_retries_exceeded" if retries >= max_retries else "",
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"notification_id": notification_id},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            raise
