from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.actors.models import Actor
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.posts.models import Post
from apps.social.models import Block, Like, Repost
from apps.social.services import can_follow, follow_actor, unfollow_actor


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def follow_view(request: HttpRequest, handle: str) -> HttpResponse:
	follower = request.user.actor
	followee = get_object_or_404(Actor, handle=handle)
	if not can_follow(follower.id, followee.id):
		messages.error(request, "Cannot follow this account.")
		return redirect("actors:detail", handle=handle)

	follow_actor(follower, followee)
	Notification.objects.create(
		recipient=followee,
		source_actor=follower,
		notification_type=Notification.NotificationType.FOLLOW,
	)
	messages.success(request, f"You now follow @{followee.handle}.")
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
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True)
	like, created = Like.objects.get_or_create(actor=actor, post=post)
	if not created:
		like.delete()
		liked = False
	else:
		liked = True
		Notification.objects.create(
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
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True)
	repost = Repost.objects.filter(actor=actor, post=post).first()
	if repost:
		repost.delete()
		messages.success(request, "Repost removed.")
	else:
		Repost.objects.create(actor=actor, post=post)
		messages.success(request, "Post reposted.")
	return redirect(request.META.get("HTTP_REFERER", "home"))


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
	Report.objects.create(reporter=reporter, target_actor=target, reason=reason, description=description)
	messages.success(request, "Report submitted. Thank you.")
	return redirect("actors:detail", handle=handle)
