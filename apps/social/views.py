from time import perf_counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.actors.models import Actor
from apps.core.pagination import paginate_queryset
from apps.core.permissions import can_comment_on_post, can_follow_actor, can_view_post
from apps.core.services.interaction_observability import log_interaction_metric
from apps.moderation.models import Report
from apps.moderation.services import ActionVelocityTracker, AdaptiveAbuseControlService
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_if_new
from apps.posts.models import Post
from apps.social.models import Block, Bookmark, Follow, Like, Repost
from apps.social.services import approve_follow_request, follow_actor, reject_follow_request, unfollow_actor


def _wants_json(request: HttpRequest) -> bool:
	requested_with = (request.headers.get("x-requested-with") or "").lower()
	accept = (request.headers.get("accept") or "").lower()
	return requested_with == "xmlhttprequest" or "application/json" in accept


def _follow_payload(followee: Actor, *, following: bool, follow_pending: bool) -> dict[str, object]:
	if following:
		return {
			"ok": True,
			"following": True,
			"follow_pending": False,
			"next_action": "unfollow",
			"button_label": "✓ Following",
			"button_active": True,
			"message": f"You now follow @{followee.handle}.",
		}
	if follow_pending:
		return {
			"ok": True,
			"following": False,
			"follow_pending": True,
			"next_action": "unfollow",
			"button_label": "Cancel request",
			"button_active": False,
			"message": f"Follow request sent to @{followee.handle}.",
		}
	return {
		"ok": True,
		"following": False,
		"follow_pending": False,
		"next_action": "follow",
		"button_label": "＋ Follow",
		"button_active": False,
		"message": f"You unfollowed @{followee.handle}.",
	}


def _follow_request_payload(follow: Follow, *, action: str) -> dict[str, object]:
	verb = "approved" if action == "approved" else "rejected"
	return {
		"ok": True,
		"action": action,
		"follow_id": str(follow.id),
		"remove_request_row": True,
		"empty_message": "No pending follow requests.",
		"message": f"{verb.capitalize()} follow request from @{follow.follower.handle}.",
	}


def _json_action_response(
	*,
	request: HttpRequest,
	name: str,
	started_at: float,
	payload: dict[str, object],
	status: int = 200,
	success: bool = True,
	target_id: str = "",
	detail: str = "",
) -> JsonResponse:
	actor = getattr(getattr(request, "user", None), "actor", None)
	actor_id = str(actor.id) if actor is not None else ""
	log_interaction_metric(
		name=name,
		success=success,
		duration_ms=(perf_counter() - started_at) * 1000,
		status_code=status,
		actor_id=actor_id,
		target_id=target_id,
		detail=detail,
	)
	return JsonResponse(payload, status=status)


def _deny_if_abuse_limited(
	request: HttpRequest,
	*,
	action_name: str,
	started_at: float,
	actor: Actor,
	target_id: str,
	denial_detail: str,
	fallback_redirect: str,
	ui_message: str,
) -> HttpResponse | None:
	allowed, denial_reason = AdaptiveAbuseControlService.evaluate_action(actor, action_name)
	if allowed:
		return None

	if _wants_json(request):
		return _json_action_response(
			request=request,
			name=f"social_{action_name}",
			started_at=started_at,
			payload={"ok": False, "error": denial_reason},
			status=429,
			success=False,
			target_id=target_id,
			detail=denial_detail,
		)

	messages.error(request, ui_message)
	return redirect(fallback_redirect)


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def follow_view(request: HttpRequest, handle: str) -> HttpResponse:
	started_at = perf_counter()
	follower = request.user.actor
	followee = get_object_or_404(Actor, handle=handle)
	denied_response = _deny_if_abuse_limited(
		request,
		action_name="follow",
		started_at=started_at,
		actor=follower,
		target_id=str(followee.id),
		denial_detail="abuse_control",
		fallback_redirect=f"/actors/{handle}/",
		ui_message="Follow temporarily limited due to account risk controls.",
	)
	if denied_response is not None:
		return denied_response
	if not can_follow_actor(follower, followee):
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_follow",
				started_at=started_at,
				payload={"ok": False, "error": "Cannot follow this account."},
				status=403,
				success=False,
				target_id=str(followee.id),
				detail="permission_denied",
			)
		messages.error(request, "Cannot follow this account.")
		return redirect("actors:detail", handle=handle)

	follow_actor(follower, followee)
	ActionVelocityTracker.record_follow(follower)
	follow = Follow.objects.get(follower=follower, followee=followee)
	if follow.state == Follow.FollowState.ACCEPTED:
		create_notification_if_new(
			recipient=followee,
			source_actor=follower,
			notification_type=Notification.NotificationType.FOLLOW,
		)
		messages.success(request, f"You now follow @{followee.handle}.")
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_follow",
				started_at=started_at,
				payload=_follow_payload(followee, following=True, follow_pending=False),
				target_id=str(followee.id),
			)
	else:
		messages.success(request, f"Follow request sent to @{followee.handle}.")
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_follow",
				started_at=started_at,
				payload=_follow_payload(followee, following=False, follow_pending=True),
				target_id=str(followee.id),
			)
	return redirect("actors:detail", handle=handle)


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def unfollow_view(request: HttpRequest, handle: str) -> HttpResponse:
	started_at = perf_counter()
	follower = request.user.actor
	followee = get_object_or_404(Actor, handle=handle)
	unfollow_actor(follower, followee)
	messages.success(request, f"You unfollowed @{followee.handle}.")
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_unfollow",
			started_at=started_at,
			payload=_follow_payload(followee, following=False, follow_pending=False),
			target_id=str(followee.id),
		)
	return redirect("actors:detail", handle=handle)


@ratelimit(key="user_or_ip", rate="30/h", block=True)
@login_required
@require_POST
def block_view(request: HttpRequest, handle: str) -> HttpResponse:
	blocker = request.user.actor
	blocked = get_object_or_404(Actor, handle=handle)
	if blocker.id == blocked.id:
		messages.error(request, "You cannot block yourself.")
		return redirect("actors:detail", handle=handle)
	Block.objects.get_or_create(blocker=blocker, blocked=blocked)
	# Also unfollow in both directions
	unfollow_actor(blocker, blocked)
	unfollow_actor(blocked, blocker)
	messages.success(request, f"@{blocked.handle} has been blocked.")
	return redirect("home")


@ratelimit(key="user_or_ip", rate="30/h", block=True)
@login_required
@require_POST
def unblock_view(request: HttpRequest, handle: str) -> HttpResponse:
	blocker = request.user.actor
	blocked = get_object_or_404(Actor, handle=handle)
	Block.objects.filter(blocker=blocker, blocked=blocked).delete()
	messages.success(request, f"@{blocked.handle} has been unblocked.")
	return redirect("actors:detail", handle=handle)


@ratelimit(key="user_or_ip", rate="120/h", block=True)
@login_required
@require_POST
def like_toggle_view(request: HttpRequest, post_id: str) -> HttpResponse:
	started_at = perf_counter()
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if not can_comment_on_post(actor, post):
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_like_toggle",
				started_at=started_at,
				payload={"ok": False, "error": "You cannot engage with this post."},
				status=403,
				success=False,
				target_id=str(post.id),
				detail="permission_denied",
			)
		messages.error(request, "You cannot engage with this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	like, created = Like.objects.get_or_create(actor=actor, post=post)
	if not created:
		like.delete()
		liked = False
	else:
		denied_response = _deny_if_abuse_limited(
			request,
			action_name="like",
			started_at=started_at,
			actor=actor,
			target_id=str(post.id),
			denial_detail="abuse_control",
			fallback_redirect=request.META.get("HTTP_REFERER", "home"),
			ui_message="Like temporarily limited due to account risk controls.",
		)
		if denied_response is not None:
			like.delete()
			return denied_response
		liked = True
		ActionVelocityTracker.record_like(actor)
		create_notification_if_new(
			recipient=post.author,
			source_actor=actor,
			notification_type=Notification.NotificationType.LIKE,
			source_post=post,
		)
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_like_toggle",
			started_at=started_at,
			payload={"ok": True, "liked": liked, "like_count": post.like_count},
			target_id=str(post.id),
		)
	return redirect(request.META.get("HTTP_REFERER", "home"))


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def repost_toggle_view(request: HttpRequest, post_id: str) -> HttpResponse:
	started_at = perf_counter()
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if actor.id == post.author_id:
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_repost_toggle",
				started_at=started_at,
				payload={"ok": False, "error": "You cannot repost your own post."},
				status=400,
				success=False,
				target_id=str(post.id),
				detail="self_repost",
			)
		messages.error(request, "You cannot repost your own post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	if not can_comment_on_post(actor, post):
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_repost_toggle",
				started_at=started_at,
				payload={"ok": False, "error": "You cannot repost this post."},
				status=403,
				success=False,
				target_id=str(post.id),
				detail="permission_denied",
			)
		messages.error(request, "You cannot repost this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	repost = Repost.objects.filter(actor=actor, post=post).first()
	if repost:
		repost.delete()
		reposted = False
		messages.success(request, "Repost removed.")
	else:
		denied_response = _deny_if_abuse_limited(
			request,
			action_name="repost",
			started_at=started_at,
			actor=actor,
			target_id=str(post.id),
			denial_detail="abuse_control",
			fallback_redirect=request.META.get("HTTP_REFERER", "home"),
			ui_message="Repost temporarily limited due to account risk controls.",
		)
		if denied_response is not None:
			return denied_response
		try:
			_, created = Repost.objects.get_or_create(actor=actor, post=post)
		except IntegrityError:
			created = False
		if not created:
			if _wants_json(request):
				return _json_action_response(
					request=request,
					name="social_repost_toggle",
					started_at=started_at,
					payload={"ok": False, "error": "Post already reposted."},
					status=400,
					success=False,
					target_id=str(post.id),
					detail="already_reposted",
				)
			messages.info(request, "Post already reposted.")
			return redirect(request.META.get("HTTP_REFERER", "home"))
		reposted = True
		ActionVelocityTracker.record_repost(actor)
		create_notification_if_new(
			recipient=post.author,
			source_actor=actor,
			notification_type=Notification.NotificationType.REPOST,
			source_post=post,
		)
		messages.success(request, "Post reposted.")
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_repost_toggle",
			started_at=started_at,
			payload={"ok": True, "reposted": reposted, "repost_count": post.repost_count},
			target_id=str(post.id),
		)
	return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
@require_http_methods(["GET"])
def social_index_view(request: HttpRequest) -> HttpResponse:
	return redirect("social:follow-requests")


@ratelimit(key="user_or_ip", rate="20/h", block=True)
@login_required
@require_POST
def report_actor_view(request: HttpRequest, handle: str) -> HttpResponse:
	reporter = request.user.actor
	target = get_object_or_404(Actor, handle=handle)
	reason = request.POST.get("reason", "unspecified")
	description = request.POST.get("description", "")
	if reporter.id == target.id:
		messages.error(request, "You cannot report yourself.")
		return redirect("actors:detail", handle=handle)
	Report.objects.create(
		reporter=reporter,
		target_actor=target,
		reason=Report.normalize_reason(reason),
		severity=Report.severity_for_reason(reason),
		description=description,
	)
	messages.success(request, "Report submitted. Thank you.")
	return redirect("actors:detail", handle=handle)


@ratelimit(key="user_or_ip", rate="120/h", block=True)
@login_required
@require_POST
def bookmark_toggle_view(request: HttpRequest, post_id: str) -> HttpResponse:
	started_at = perf_counter()
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if not can_view_post(actor, post):
		if _wants_json(request):
			return _json_action_response(
				request=request,
				name="social_bookmark_toggle",
				started_at=started_at,
				payload={"ok": False, "error": "You cannot bookmark this post."},
				status=403,
				success=False,
				target_id=str(post.id),
				detail="permission_denied",
			)
		messages.error(request, "You cannot bookmark this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))

	bookmark, created = Bookmark.objects.get_or_create(actor=actor, post=post)
	if not created:
		bookmark.delete()
		bookmarked = False
		messages.success(request, "Bookmark removed.")
	else:
		bookmarked = True
		messages.success(request, "Post bookmarked.")
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_bookmark_toggle",
			started_at=started_at,
			payload={"ok": True, "bookmarked": bookmarked},
			target_id=str(post.id),
		)
	return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
@require_http_methods(["GET"])
def bookmarks_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	bookmarks_qs = Bookmark.objects.filter(actor=actor).select_related("post", "post__author", "post__author__profile").prefetch_related("post__attachments").order_by("-created_at")
	visible_posts = [item.post for item in bookmarks_qs if can_view_post(actor, item.post)]
	page_obj = paginate_queryset(request, visible_posts, per_page=20, page_param="page")
	posts = page_obj.object_list
	liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	return render(
		request,
		"social/bookmarks.html",
		{
			"posts": posts,
			"page_obj": page_obj,
			"liked_ids": liked_ids,
			"reposted_ids": reposted_ids,
			"bookmarked_ids": bookmarked_ids,
		},
	)


@login_required
def follow_requests_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	pending_requests = Follow.objects.filter(
		followee=actor,
		state=Follow.FollowState.PENDING,
	).select_related("follower", "follower__profile").order_by("-created_at")
	return render(request, "social/follow_requests.html", {"pending_requests": pending_requests})


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def approve_follow_request_view(request: HttpRequest, follow_id: str) -> HttpResponse:
	started_at = perf_counter()
	actor = request.user.actor
	follow = get_object_or_404(Follow, id=follow_id, followee=actor, state=Follow.FollowState.PENDING)
	approve_follow_request(follow)
	create_notification_if_new(
		recipient=follow.follower,
		source_actor=follow.followee,
		notification_type=Notification.NotificationType.FOLLOW,
	)
	messages.success(request, f"Approved follow request from @{follow.follower.handle}.")
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_follow_request_approve",
			started_at=started_at,
			payload=_follow_request_payload(follow, action="approved"),
			target_id=str(follow.id),
		)
	return redirect("social:follow-requests")


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def reject_follow_request_view(request: HttpRequest, follow_id: str) -> HttpResponse:
	started_at = perf_counter()
	actor = request.user.actor
	follow = get_object_or_404(Follow, id=follow_id, followee=actor, state=Follow.FollowState.PENDING)
	reject_follow_request(follow)
	messages.success(request, f"Rejected follow request from @{follow.follower.handle}.")
	if _wants_json(request):
		return _json_action_response(
			request=request,
			name="social_follow_request_reject",
			started_at=started_at,
			payload=_follow_request_payload(follow, action="rejected"),
			target_id=str(follow.id),
		)
	return redirect("social:follow-requests")
