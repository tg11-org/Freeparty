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
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_if_new
from apps.posts.models import Post
from apps.social.models import Block, Bookmark, Follow, Like, Repost
from apps.social.services import approve_follow_request, follow_actor, reject_follow_request, unfollow_actor


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def follow_view(request: HttpRequest, handle: str) -> HttpResponse:
	follower = request.user.actor
	followee = get_object_or_404(Actor, handle=handle)
	if not can_follow_actor(follower, followee):
		messages.error(request, "Cannot follow this account.")
		return redirect("actors:detail", handle=handle)

	follow_actor(follower, followee)
	follow = Follow.objects.get(follower=follower, followee=followee)
	if follow.state == Follow.FollowState.ACCEPTED:
		create_notification_if_new(
			recipient=followee,
			source_actor=follower,
			notification_type=Notification.NotificationType.FOLLOW,
		)
		messages.success(request, f"You now follow @{followee.handle}.")
	else:
		messages.success(request, f"Follow request sent to @{followee.handle}.")
	return redirect("actors:detail", handle=handle)


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def unfollow_view(request: HttpRequest, handle: str) -> HttpResponse:
	follower = request.user.actor
	followee = get_object_or_404(Actor, handle=handle)
	unfollow_actor(follower, followee)
	messages.success(request, f"You unfollowed @{followee.handle}.")
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
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if not can_comment_on_post(actor, post):
		messages.error(request, "You cannot engage with this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	like, created = Like.objects.get_or_create(actor=actor, post=post)
	if not created:
		like.delete()
		liked = False
	else:
		liked = True
		create_notification_if_new(
			recipient=post.author,
			source_actor=actor,
			notification_type=Notification.NotificationType.LIKE,
			source_post=post,
		)
	if request.headers.get("x-requested-with") == "XMLHttpRequest":
		return JsonResponse({"liked": liked, "like_count": post.like_count})
	return redirect(request.META.get("HTTP_REFERER", "home"))


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def repost_toggle_view(request: HttpRequest, post_id: str) -> HttpResponse:
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if actor.id == post.author_id:
		messages.error(request, "You cannot repost your own post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	if not can_comment_on_post(actor, post):
		messages.error(request, "You cannot repost this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))
	repost = Repost.objects.filter(actor=actor, post=post).first()
	if repost:
		repost.delete()
		messages.success(request, "Repost removed.")
	else:
		try:
			_, created = Repost.objects.get_or_create(actor=actor, post=post)
		except IntegrityError:
			created = False
		if not created:
			messages.info(request, "Post already reposted.")
			return redirect(request.META.get("HTTP_REFERER", "home"))
		create_notification_if_new(
			recipient=post.author,
			source_actor=actor,
			notification_type=Notification.NotificationType.REPOST,
			source_post=post,
		)
		messages.success(request, "Post reposted.")
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
	actor = request.user.actor
	post = get_object_or_404(Post, id=post_id)
	if not can_view_post(actor, post):
		messages.error(request, "You cannot bookmark this post.")
		return redirect(request.META.get("HTTP_REFERER", "home"))

	bookmark, created = Bookmark.objects.get_or_create(actor=actor, post=post)
	if not created:
		bookmark.delete()
		messages.success(request, "Bookmark removed.")
	else:
		messages.success(request, "Post bookmarked.")
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
	actor = request.user.actor
	follow = get_object_or_404(Follow, id=follow_id, followee=actor, state=Follow.FollowState.PENDING)
	approve_follow_request(follow)
	create_notification_if_new(
		recipient=follow.follower,
		source_actor=follow.followee,
		notification_type=Notification.NotificationType.FOLLOW,
	)
	messages.success(request, f"Approved follow request from @{follow.follower.handle}.")
	return redirect("social:follow-requests")


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def reject_follow_request_view(request: HttpRequest, follow_id: str) -> HttpResponse:
	actor = request.user.actor
	follow = get_object_or_404(Follow, id=follow_id, followee=actor, state=Follow.FollowState.PENDING)
	reject_follow_request(follow)
	messages.success(request, f"Rejected follow request from @{follow.follower.handle}.")
	return redirect("social:follow-requests")
