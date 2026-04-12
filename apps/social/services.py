from apps.social.models import Block, Follow


def can_follow(follower_id, followee_id) -> bool:
    if follower_id == followee_id:
        return False
    if Block.objects.filter(blocker_id=followee_id, blocked_id=follower_id).exists():
        return False
    if Block.objects.filter(blocker_id=follower_id, blocked_id=followee_id).exists():
        return False
    return True


def follow_actor(follower, followee) -> Follow:
    state = Follow.FollowState.ACCEPTED
    follow, _ = Follow.objects.update_or_create(
        follower=follower,
        followee=followee,
        defaults={"state": state},
    )
    return follow


def unfollow_actor(follower, followee) -> None:
    Follow.objects.filter(follower=follower, followee=followee).update(state=Follow.FollowState.REMOVED)
