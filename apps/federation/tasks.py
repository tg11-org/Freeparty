from celery import shared_task
from django.utils import timezone

from apps.core.services.task_observability import observe_celery_task
from apps.core.services.task_reliability import (
    mark_task_execution_failed,
    mark_task_execution_succeeded,
    start_task_execution,
)
from apps.federation.models import FederationDelivery


@shared_task(bind=True, max_retries=5)
def execute_federation_delivery(self, delivery_id: str, correlation_id: str | None = None) -> None:
    idempotency_key = f"federation_delivery:{delivery_id}"
    execution, should_skip = start_task_execution(
        task_name=self.name,
        idempotency_key=idempotency_key,
        task_id=getattr(self.request, "id", ""),
        correlation_id=correlation_id,
        payload={"delivery_id": delivery_id},
    )
    if should_skip:
        return

    with observe_celery_task(self, correlation_id=correlation_id):
        try:
            delivery = FederationDelivery.objects.get(id=delivery_id)
            if delivery.state == FederationDelivery.DeliveryState.SUCCESS:
                mark_task_execution_succeeded(execution)
                return

            # Placeholder for signed ActivityPub delivery implementation.
            # For now, we mark successful processing and preserve retry metadata.
            delivery.retry_count = max(delivery.retry_count, getattr(self.request, "retries", 0))
            delivery.last_attempted_at = timezone.now()
            delivery.state = FederationDelivery.DeliveryState.SUCCESS
            delivery.response_code = 202
            delivery.response_body = "queued_for_delivery"
            delivery.save(
                update_fields=[
                    "retry_count",
                    "last_attempted_at",
                    "state",
                    "response_code",
                    "response_body",
                    "updated_at",
                ]
            )
            mark_task_execution_succeeded(execution)
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"delivery_id": delivery_id},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            raise
