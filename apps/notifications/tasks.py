from celery import shared_task

from apps.notifications.models import Notification


@shared_task
def process_notification_fanout(notification_id: str) -> None:
    # Placeholder for future fanout-on-write and websocket publish.
    Notification.objects.filter(id=notification_id).exists()
