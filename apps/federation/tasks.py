from celery import shared_task

from apps.federation.models import FederationDelivery


@shared_task(bind=True, max_retries=5)
def execute_federation_delivery(self, delivery_id: str) -> None:
    delivery = FederationDelivery.objects.get(id=delivery_id)
    # Placeholder for signed ActivityPub delivery implementation.
    delivery.retry_count += 1
    delivery.state = FederationDelivery.DeliveryState.RETRYING
    delivery.save(update_fields=["retry_count", "state", "updated_at"])
