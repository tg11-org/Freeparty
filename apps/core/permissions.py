from __future__ import annotations

from typing import Optional

from django.contrib.auth.base_user import AbstractBaseUser

from apps.actors.models import Actor
from apps.posts.models import Comment, Post
from apps.profiles.models import Profile
from apps.social.models import Block, Follow


SUPPORT_USER_INFO_PERMISSION = "accounts.view_support_user_info"
SUPPORT_RESEND_VERIFICATION_PERMISSION = "accounts.resend_verification_email"
SUPPORT_ACCOUNT_LIFECYCLE_PERMISSION = "accounts.manage_account_lifecycle_support"
MODERATION_DASHBOARD_PERMISSION = "moderation.access_moderation_dashboard"
REPORT_REVIEW_PERMISSION = "moderation.review_reports"
MODERATION_ACTION_PERMISSION = "moderation.manage_moderation_actions"
AUDIT_SUMMARY_PERMISSION = "moderation.view_audit_summary"
SECURITY_AUDIT_PERMISSION = "moderation.view_security_audit_events"
TRUST_SIGNAL_PERMISSION = "moderation.manage_trust_signals"
SUPPORT_DIAGNOSTICS_PERMISSION = "core.view_support_diagnostics"
SECURITY_POSTURE_PERMISSION = "core.view_security_posture"
EMAIL_DIAGNOSTICS_PERMISSION = "core.run_email_diagnostics"


def has_any_permission(user: Optional[AbstractBaseUser], *permissions: str) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return any(user.has_perm(permission) for permission in permissions)


def can_access_support_user_info(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, SUPPORT_USER_INFO_PERMISSION)


def can_resend_verification(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, SUPPORT_RESEND_VERIFICATION_PERMISSION)


def can_manage_account_lifecycle_support(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, SUPPORT_ACCOUNT_LIFECYCLE_PERMISSION)


def can_access_moderation_dashboard(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, MODERATION_DASHBOARD_PERMISSION, REPORT_REVIEW_PERMISSION, MODERATION_ACTION_PERMISSION)


def can_review_reports(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, REPORT_REVIEW_PERMISSION)


def can_manage_moderation_actions(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, MODERATION_ACTION_PERMISSION)


def can_view_audit_summary(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, AUDIT_SUMMARY_PERMISSION)


def can_view_security_audit_events(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, SECURITY_AUDIT_PERMISSION)


def can_manage_trust_signals(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, TRUST_SIGNAL_PERMISSION)


def can_view_security_posture(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, SECURITY_POSTURE_PERMISSION)


def can_run_email_diagnostics(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, EMAIL_DIAGNOSTICS_PERMISSION)


def can_view_security_triage(user: Optional[AbstractBaseUser]) -> bool:
    return has_any_permission(user, REPORT_REVIEW_PERMISSION, SECURITY_AUDIT_PERMISSION, TRUST_SIGNAL_PERMISSION)


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
