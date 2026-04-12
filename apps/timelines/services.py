from __future__ import annotations

from django.db.models import QuerySet

from apps.posts.models import Post
from apps.social.models import Follow


def public_timeline(limit: int = 50) -> QuerySet[Post]:
    return (
        Post.objects.filter(
            visibility=Post.Visibility.PUBLIC,
            deleted_at__isnull=True,
            moderation_state=Post.ModerationState.NORMAL,
        )
        .select_related("author")
        .order_by("-created_at")[:limit]
    )


def home_timeline(actor_id, limit: int = 50) -> QuerySet[Post]:
    followed_ids = Follow.objects.filter(
        follower_id=actor_id,
        state=Follow.FollowState.ACCEPTED,
    ).values_list("followee_id", flat=True)

    return (
        Post.objects.filter(
            author_id__in=followed_ids,
            deleted_at__isnull=True,
        )
        .exclude(moderation_state=Post.ModerationState.TAKEN_DOWN)
        .select_related("author")
        .order_by("-created_at")[:limit]
    )
