from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.actors.models import Actor
from apps.notifications.models import Notification
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
