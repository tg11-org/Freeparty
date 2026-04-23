from django.core.exceptions import ObjectDoesNotExist

from apps.social.models import Block, Follow


def can_follow(follower_id, followee_id) -> bool:
    if follower_id == followee_id:
        return False
    if Block.objects.filter(blocker_id=followee_id, blocked_id=follower_id).exists():
        return False
    if Block.objects.filter(blocker_id=follower_id, blocked_id=followee_id).exists():
        return False
    return True


def can_follow_actor(follower_id, followee_id) -> bool:
    return can_follow(follower_id=follower_id, followee_id=followee_id)


def follow_actor(follower, followee) -> Follow:
    is_private = False
    try:
        is_private = bool(followee.profile.is_private_account)
    except ObjectDoesNotExist:
        is_private = False
    state = Follow.FollowState.PENDING if is_private else Follow.FollowState.ACCEPTED
    follow, _ = Follow.objects.update_or_create(
        follower=follower,
        followee=followee,
        defaults={"state": state},
    )
    return follow


def unfollow_actor(follower, followee) -> None:
    Follow.objects.filter(follower=follower, followee=followee).update(state=Follow.FollowState.REMOVED)


def approve_follow_request(follow: Follow) -> Follow:
    follow.state = Follow.FollowState.ACCEPTED
    follow.save(update_fields=["state", "updated_at"])
    return follow


def reject_follow_request(follow: Follow) -> Follow:
    follow.state = Follow.FollowState.REJECTED
    follow.save(update_fields=["state", "updated_at"])
    return follow
