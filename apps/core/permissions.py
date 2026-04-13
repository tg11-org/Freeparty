from __future__ import annotations

from typing import Optional

from apps.actors.models import Actor
from apps.posts.models import Comment, Post
from apps.profiles.models import Profile
from apps.social.models import Block, Follow


def _is_blocked_either_way(actor_a: Actor, actor_b: Actor) -> bool:
    return Block.objects.filter(blocker=actor_a, blocked=actor_b).exists() or Block.objects.filter(
        blocker=actor_b, blocked=actor_a
    ).exists()


def _is_private_account(actor: Actor) -> bool:
    return Profile.objects.filter(actor=actor, is_private_account=True).exists()


def _is_accepted_follower(follower: Actor, followee: Actor) -> bool:
    return Follow.objects.filter(
        follower=follower,
        followee=followee,
        state=Follow.FollowState.ACCEPTED,
    ).exists()


def can_view_actor(viewer: Optional[Actor], target: Actor) -> bool:
    if target.state != Actor.ActorState.ACTIVE:
        return False
    if viewer is None:
        return not _is_private_account(target)
    if viewer.id == target.id:
        return True
    if _is_blocked_either_way(viewer, target):
        return False
    if _is_private_account(target):
        return _is_accepted_follower(viewer, target)
    return True


def can_follow_actor(follower: Actor, followee: Actor) -> bool:
    if follower.id == followee.id:
        return False
    if followee.state != Actor.ActorState.ACTIVE:
        return False
    return not _is_blocked_either_way(follower, followee)


def can_view_post(viewer: Optional[Actor], post: Post) -> bool:
    if post.deleted_at is not None:
        return False
    if post.moderation_state in {Post.ModerationState.HIDDEN, Post.ModerationState.TAKEN_DOWN}:
        return False

    author = post.author
    if viewer is not None and viewer.id == author.id:
        return True

    if viewer is not None and _is_blocked_either_way(viewer, author):
        return False

    if _is_private_account(author):
        if viewer is None:
            return False
        if not _is_accepted_follower(viewer, author):
            return False

    if post.visibility in {Post.Visibility.PUBLIC, Post.Visibility.UNLISTED}:
        return True

    if post.visibility == Post.Visibility.FOLLOWERS_ONLY:
        if viewer is None:
            return False
        return _is_accepted_follower(viewer, author)

    if post.visibility == Post.Visibility.PRIVATE:
        return False

    return False


def can_edit_post(actor: Optional[Actor], post: Post) -> bool:
    if actor is None:
        return False
    if post.deleted_at is not None:
        return False
    return actor.id == post.author.id


def can_delete_post(actor: Optional[Actor], post: Post) -> bool:
    return can_edit_post(actor, post)


def can_comment_on_post(actor: Optional[Actor], post: Post) -> bool:
    if actor is None:
        return False
    return can_view_post(actor, post)


def can_edit_comment(actor: Optional[Actor], comment: Comment) -> bool:
    if actor is None:
        return False
    if comment.deleted_at is not None:
        return False
    return actor.id == comment.author.id


def can_delete_comment(actor: Optional[Actor], comment: Comment) -> bool:
    return can_edit_comment(actor, comment)
