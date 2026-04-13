from __future__ import annotations

from django.db.models import QuerySet

from apps.posts.models import Post
from apps.posts.selectors import visible_home_posts_for_actor, visible_public_posts_for_actor


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
