from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.pagination import paginate_queryset
from apps.notifications.models import Notification


def _notification_post_label(item: Notification) -> str:
	post = item.source_post
	if post is None:
		return ""
	content = (post.content or "").strip()
	if content:
		return content
	first_attachment = post.attachments.first()
	if first_attachment is not None:
		caption = (first_attachment.caption or "").strip()
		if caption:
			return caption
	return f"Post {post.id}"


def _group_notifications_by_day(notifications: list[Notification]) -> list[dict[str, object]]:
	today = timezone.localdate()
	grouped: list[dict[str, object]] = []
	for item in notifications:
		item_day = timezone.localtime(item.created_at).date()
		if item_day == today:
			label = "Today"
		elif item_day == (today - timedelta(days=1)):
			label = "Yesterday"
		else:
			label = item_day.strftime("%Y-%m-%d")

		if grouped and grouped[-1]["label"] == label:
			grouped[-1]["items"].append(item)
		else:
			grouped.append({"label": label, "items": [item]})
	return grouped


@login_required
@require_http_methods(["GET"])
def notifications_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	filter_type = request.GET.get("type", "all").strip()
	view_mode = request.GET.get("view", "flat").strip()
	grouped_view = view_mode == "grouped"
	queryset = Notification.objects.filter(recipient=actor).select_related("source_actor", "source_post").prefetch_related("source_post__attachments")
	if filter_type == "unread":
		queryset = queryset.filter(read_at__isnull=True)
	elif filter_type in {choice[0] for choice in Notification.NotificationType.choices}:
		queryset = queryset.filter(notification_type=filter_type)

	page_obj = paginate_queryset(request, queryset, per_page=20, page_param="page")
	notifications = list(page_obj.object_list)
	for item in notifications:
		item.source_post_label = _notification_post_label(item)
	grouped_notifications = _group_notifications_by_day(notifications) if grouped_view else []
	query_parts: list[str] = []
	if filter_type != "all":
		query_parts.append(f"type={filter_type}")
	if grouped_view:
		query_parts.append("view=grouped")
	query_string = "&".join(query_parts)
	return render(request, "notifications/list.html", {
		"notifications": notifications,
		"grouped_notifications": grouped_notifications,
		"grouped_view": grouped_view,
		"page_obj": page_obj,
		"filter_type": filter_type,
		"query_string": query_string,
	})


@login_required
@require_POST
def mark_all_read_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	updated = Notification.objects.filter(recipient=actor, read_at__isnull=True).update(read_at=timezone.now())
	messages.success(request, f"Marked {updated} notifications as read.")
	return redirect("notifications:list")


@login_required
@require_POST
def mark_read_view(request: HttpRequest, notification_id: str) -> HttpResponse:
	actor = request.user.actor
	notification = get_object_or_404(Notification, id=notification_id, recipient=actor)
	if notification.read_at is None:
		notification.read_at = timezone.now()
		notification.save(update_fields=["read_at"])
	return redirect("notifications:list")
