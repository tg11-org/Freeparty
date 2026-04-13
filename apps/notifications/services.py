from __future__ import annotations

import re
from datetime import timedelta

from django.utils import timezone

from apps.notifications.models import Notification

_MENTION_RE = re.compile(r"@([\w]+(?:\.[\w]+)*)", re.UNICODE)


def create_notification_if_new(
    *,
    recipient,
    notification_type: str,
    source_actor=None,
    source_post=None,
    payload: dict | None = None,
    dedupe_seconds: int = 300,
):
    payload = payload or {}
    threshold = timezone.now() - timedelta(seconds=dedupe_seconds)
    existing = Notification.objects.filter(
        recipient=recipient,
        notification_type=notification_type,
        source_actor=source_actor,
        source_post=source_post,
        created_at__gte=threshold,
    ).first()
    if existing:
        return existing, False

    notification = Notification.objects.create(
        recipient=recipient,
        source_actor=source_actor,
        source_post=source_post,
        notification_type=notification_type,
        payload=payload,
    )
    return notification, True


def notify_mentions(*, content: str, source_actor, source_post=None) -> None:
    """Parse @handles from *content* and fire MENTION notifications for local actors.

    Skips the source_actor themselves and actors without a linked user account.
    Imports are deferred to avoid circular imports at module load time.
    """
    from django.db.models.functions import Lower  # noqa: PLC0415

    from apps.actors.models import Actor  # noqa: PLC0415

    handles = {m.lower() for m in _MENTION_RE.findall(content)}
    if not handles:
        return

    mentioned_actors = (
        Actor.objects.annotate(handle_lower=Lower("handle"))
        .filter(
            handle_lower__in=handles,
            actor_type=Actor.ActorType.LOCAL,
        )
        .exclude(id=source_actor.id)
    )

    for actor in mentioned_actors:
        create_notification_if_new(
            recipient=actor,
            notification_type=Notification.NotificationType.MENTION,
            source_actor=source_actor,
            source_post=source_post,
        )
