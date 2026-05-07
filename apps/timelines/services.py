from __future__ import annotations

from django.db.models import QuerySet

from apps.posts.models import Post
from apps.posts.selectors import visible_home_posts_for_actor, visible_public_posts_for_actor


def federated_public_timeline(actor=None, max_local: int = 300, max_remote: int = 300) -> list[dict]:
    """Return a time-sorted list of dicts merging local public posts and inbound remote posts.

    Each dict has:
        is_remote (bool)
        obj       (Post | RemotePost)
        created_at (datetime)
    """
    from apps.federation.models import RemotePost

    local_qs = visible_public_posts_for_actor(actor=actor)
    local_items = [
        {"is_remote": False, "obj": p, "created_at": p.created_at}
        for p in local_qs[:max_local]
    ]

    remote_qs = (
        RemotePost.objects.filter(
            instance__allowlist_state="allowed",
            instance__is_blocked=False,
        )
        .select_related("remote_actor", "instance")
        .order_by("-created_at")[:max_remote]
    )
    remote_items = [
        {"is_remote": True, "obj": p, "created_at": p.created_at}
        for p in remote_qs
    ]

    combined = sorted(local_items + remote_items, key=lambda x: x["created_at"], reverse=True)
    return combined


def public_timeline(actor=None, limit: int | None = 50) -> QuerySet[Post]:
    qs = visible_public_posts_for_actor(actor=actor)
    if limit is None:
        return qs
    return qs[:limit]


def home_timeline(actor, limit: int | None = 50) -> QuerySet[Post]:
    qs = visible_home_posts_for_actor(actor=actor)
    if limit is None:
        return qs
    return qs[:limit]
