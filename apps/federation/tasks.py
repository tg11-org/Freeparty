import json
import urllib.error
import urllib.request

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.services.task_observability import observe_celery_task
from apps.core.services.task_reliability import (
    mark_task_execution_failed,
    mark_task_execution_succeeded,
    start_task_execution,
)
from apps.core.network import safe_urlopen
from apps.federation.models import FederationDelivery
from apps.federation.signing import build_signed_headers


def federation_retry_delay_seconds(retry_count: int) -> int:
    schedule = [60, 300, 1800, 7200]
    index = min(max(retry_count, 0), len(schedule) - 1)
    return schedule[index]


@shared_task(bind=True, max_retries=5)
def execute_federation_delivery(self, delivery_id: str, correlation_id: str | None = None) -> None:
    if not getattr(settings, "FEATURE_FEDERATION_OUTBOUND_ENABLED", False):
        return

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

            inbox_url = delivery.target_instance.metadata.get("inbox_url") or f"https://{delivery.target_instance.domain}/inbox"
            payload_bytes = json.dumps(delivery.activity_payload, sort_keys=True).encode("utf-8")
            shared_secret = delivery.target_instance.metadata.get("shared_secret") or getattr(settings, "FEDERATION_SHARED_SECRET", "")
            headers = build_signed_headers(
                payload=payload_bytes,
                key_id=f"freeparty:{delivery.target_instance.domain}",
                shared_secret=shared_secret,
            )
            request = urllib.request.Request(
                inbox_url,
                data=payload_bytes,
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            )
            with safe_urlopen(
                request,
                timeout=10,
                allowed_domain=delivery.target_instance.domain,
                allow_http=False,
                allow_redirects=True,
            ) as response:
                response_code = getattr(response, "status", 202)
                response_body = response.read().decode("utf-8", errors="replace")[:500]

            delivery.retry_count = max(delivery.retry_count, getattr(self.request, "retries", 0))
            delivery.last_attempted_at = timezone.now()
            delivery.state = FederationDelivery.DeliveryState.SUCCESS
            delivery.response_code = response_code
            delivery.response_body = response_body or "delivered"
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
        except urllib.error.HTTPError as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            status_code = getattr(exc, "code", 0)
            terminal = 400 <= status_code < 500 and status_code != 429
            FederationDelivery.objects.filter(id=delivery_id).update(
                retry_count=retries + 1,
                last_attempted_at=timezone.now(),
                state=FederationDelivery.DeliveryState.FAILED if terminal else FederationDelivery.DeliveryState.RETRYING,
                response_code=status_code,
                response_body=str(exc),
            )
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=terminal or retries >= max_retries,
                terminal_reason="max_retries_exceeded" if retries >= max_retries else ("other" if terminal else ""),
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"delivery_id": delivery_id, "args": [delivery_id], "kwargs": {"correlation_id": correlation_id} if correlation_id else {}},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            if not terminal and retries < max_retries and not getattr(self.request, "called_directly", False):
                raise self.retry(exc=exc, countdown=federation_retry_delay_seconds(retries))
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            FederationDelivery.objects.filter(id=delivery_id).update(
                retry_count=retries + 1,
                last_attempted_at=timezone.now(),
                state=FederationDelivery.DeliveryState.FAILED if retries >= max_retries else FederationDelivery.DeliveryState.RETRYING,
                response_body=str(exc),
            )
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                terminal_reason="max_retries_exceeded" if retries >= max_retries else "",
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"delivery_id": delivery_id, "args": [delivery_id], "kwargs": {"correlation_id": correlation_id} if correlation_id else {}},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            if retries < max_retries and not getattr(self.request, "called_directly", False):
                raise self.retry(exc=exc, countdown=federation_retry_delay_seconds(retries))
