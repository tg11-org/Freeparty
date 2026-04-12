from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.notifications.models import Notification


@login_required
@require_http_methods(["GET"])
def notifications_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	notifications = Notification.objects.filter(recipient=actor).select_related("source_actor", "source_post")[:100]
	return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
@require_POST
def mark_all_read_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	updated = Notification.objects.filter(recipient=actor, read_at__isnull=True).update(read_at=timezone.now())
	messages.success(request, f"Marked {updated} notifications as read.")
	return redirect("notifications:list")
