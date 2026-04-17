from __future__ import annotations

from django.db.models import Q
from django.db.models import QuerySet

from apps.posts.models import Post
from apps.social.models import Block, Follow


def visible_public_posts_for_actor(actor=None) -> QuerySet[Post]:
    qs = Post.objects.filter(
        visibility=Post.Visibility.PUBLIC,
        deleted_at__isnull=True,
        moderation_state=Post.ModerationState.NORMAL,
    )
    if actor is None:
        qs = qs.filter(author__profile__is_private_account=False)
    else:
        followed_ids = Follow.objects.filter(
            follower=actor,
            state=Follow.FollowState.ACCEPTED,
        ).values_list("followee_id", flat=True)
        qs = qs.filter(
            Q(author__profile__is_private_account=False) | Q(author_id__in=followed_ids) | Q(author=actor)
        )
    if actor is not None:
        blocked_by_me = Block.objects.filter(blocker=actor).values_list("blocked_id", flat=True)
        blocked_me = Block.objects.filter(blocked=actor).values_list("blocker_id", flat=True)
        qs = qs.exclude(author_id__in=blocked_by_me).exclude(author_id__in=blocked_me)
    return qs.select_related("author", "author__profile", "link_preview").prefetch_related("attachments").order_by("-created_at")


def visible_home_posts_for_actor(actor) -> QuerySet[Post]:
    followed_ids = Follow.objects.filter(
        follower=actor,
        state=Follow.FollowState.ACCEPTED,
    ).values_list("followee_id", flat=True)

    blocked_by_me = Block.objects.filter(blocker=actor).values_list("blocked_id", flat=True)
    blocked_me = Block.objects.filter(blocked=actor).values_list("blocker_id", flat=True)

    return (
        Post.objects.filter(
            author_id__in=followed_ids,
            deleted_at__isnull=True,
        )
        .exclude(moderation_state__in=[Post.ModerationState.HIDDEN, Post.ModerationState.TAKEN_DOWN])
        .exclude(author_id__in=blocked_by_me)
        .exclude(author_id__in=blocked_me)
        .select_related("author", "author__profile", "link_preview")
        .prefetch_related("attachments")
        .order_by("-created_at")
    )
