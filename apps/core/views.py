from urllib.parse import urlencode
import traceback

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import EmailMessage, get_connection
from django.db import connections
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.forms import EmailDiagnosticsForm, SupportRequestForm
from apps.core.pagination import paginate_queryset
from apps.notifications.models import Notification
from apps.private_messages.models import EncryptedMessageEnvelope
from apps.private_messages.services import (
	get_conversation_queryset_for_actor,
	get_unread_conversation_count,
	is_private_messages_enabled,
	populate_conversation_activity,
)
from apps.social.models import Bookmark, Like, Repost
from apps.timelines.services import home_timeline, public_timeline


def _notification_activity_summary(notification: Notification, actor_label: str) -> str:
	custom_summary = notification.payload.get("summary") if isinstance(notification.payload, dict) else ""
	if custom_summary:
		return custom_summary

	actor_prefix = actor_label or "Someone"
	phrases = {
		Notification.NotificationType.FOLLOW: f"{actor_prefix} followed you",
		Notification.NotificationType.LIKE: f"{actor_prefix} liked your post",
		Notification.NotificationType.REPLY: f"{actor_prefix} replied to your post",
		Notification.NotificationType.MENTION: f"{actor_prefix} mentioned you",
		Notification.NotificationType.REPOST: f"{actor_prefix} reposted your post",
		Notification.NotificationType.VERIFICATION: "Verification update",
		Notification.NotificationType.MODERATION: "Moderation update",
		Notification.NotificationType.SYSTEM: "System update",
	}
	return phrases.get(notification.notification_type, f"{notification.get_notification_type_display()} activity")


@require_http_methods(["GET"])
def home_view(request: HttpRequest) -> HttpResponse:
	active_tab = request.GET.get("tab", "all").strip().lower()
	if active_tab not in {"all", "media", "links"}:
		active_tab = "all"

	if request.user.is_authenticated and hasattr(request.user, "actor"):
		posts_qs = home_timeline(request.user.actor, limit=None)
		actor = request.user.actor
	else:
		posts_qs = public_timeline(limit=None)
		liked_ids = set()
		reposted_ids = set()

	if active_tab == "media":
		posts_qs = posts_qs.filter(
			attachments__attachment_type__in=["image", "video"],
			attachments__moderation_state="normal",
		).distinct()
	elif active_tab == "links":
		posts_qs = posts_qs.filter(link_preview__isnull=False)

	page_obj = paginate_queryset(request, posts_qs, per_page=20, page_param="page")
	posts = page_obj.object_list
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	else:
		bookmarked_ids = set()
	return render(request, "core/home.html", {
		"posts": posts,
		"page_obj": page_obj,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"active_tab": active_tab,
		"query_string": f"tab={active_tab}" if active_tab != "all" else "",
	})


@require_http_methods(["GET"])
def health_live_view(request: HttpRequest) -> JsonResponse:
	return JsonResponse({"status": "ok", "service": "freeparty", "check": "live"}, status=200)


@require_http_methods(["GET"])
def health_ready_view(request: HttpRequest) -> JsonResponse:
	checks = {"database": False, "cache": False}

	try:
		with connections["default"].cursor() as cursor:
			cursor.execute("SELECT 1")
		checks["database"] = True
	except Exception:
		checks["database"] = False

	try:
		cache.set("healthcheck", "ok", timeout=5)
		checks["cache"] = cache.get("healthcheck") == "ok"
	except Exception:
		checks["cache"] = False

	is_ready = all(checks.values())
	return JsonResponse(
		{"status": "ok" if is_ready else "degraded", "service": "freeparty", "check": "ready", "checks": checks},
		status=200 if is_ready else 503,
	)


@require_http_methods(["GET"])
def health_status_view(request: HttpRequest) -> HttpResponse:
	checks = {"database": False, "cache": False}

	try:
		with connections["default"].cursor() as cursor:
			cursor.execute("SELECT 1")
		checks["database"] = True
	except Exception:
		checks["database"] = False

	try:
		cache.set("healthcheck", "ok", timeout=5)
		checks["cache"] = cache.get("healthcheck") == "ok"
	except Exception:
		checks["cache"] = False

	overall = "ok" if all(checks.values()) else "degraded"
	return render(request, "core/health_status.html", {"checks": checks, "overall": overall})


@require_http_methods(["GET"])
def about_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/about.html")


@require_http_methods(["GET"])
def changelog_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/changelog.html")


@require_http_methods(["GET"])
def terms_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/terms.html")


@require_http_methods(["GET"])
def privacy_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/privacy.html")


@require_http_methods(["GET"])
def guidelines_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/guidelines.html")


@require_http_methods(["GET"])
def faq_view(request: HttpRequest) -> HttpResponse:
	return render(request, "core/faq.html")


@require_http_methods(["GET", "POST"])
def support_view(request: HttpRequest) -> HttpResponse:
	initial = {}
	if request.user.is_authenticated:
		initial["email"] = request.user.email or ""
		if hasattr(request.user, "actor"):
			initial["username"] = request.user.actor.handle

	form = SupportRequestForm(request.POST or None, initial=initial)
	mailto_url = ""
	if request.method == "POST" and form.is_valid():
		support_type_label = form.support_type_label()
		subject = f"[{support_type_label}] {form.cleaned_data['subject_summary'].strip()}"
		body_lines = [
			f"Support type: {support_type_label}",
			f"Username: {form.cleaned_data['username'].strip() or '(not provided)'}",
			f"Reply email: {form.cleaned_data['email'].strip()}",
			"",
			"Message:",
			form.cleaned_data["message"].strip(),
		]
		query = urlencode({"subject": subject, "body": "\n".join(body_lines)})
		mailto_url = f"mailto:support@tg11.org?{query}"

	return render(
		request,
		"core/support.html",
		{
			"support_form": form,
			"mailto_url": mailto_url,
			"support_email": "support@tg11.org",
		},
	)


@login_required
@require_http_methods(["GET", "POST"])
def email_test_view(request: HttpRequest) -> HttpResponse:
	if not (request.user.is_staff or request.user.is_superuser):
		return HttpResponseForbidden("Staff or superuser access required.")

	recipients = ["gage@tg11.org", "skittlesallday12@icloud.com"]
	logs: list[str] = []
	result = ""
	endpoint_results: list[dict[str, str]] = []

	endpoint_candidates = [
		str(getattr(settings, "EMAIL_HOST", "") or "").strip(),
		str(getattr(settings, "MAIL_SERVER_HOST", "") or "").strip(),
		str(getattr(settings, "MAIL_SERVER_IPV4", "") or "").strip(),
		str(getattr(settings, "MAIL_SERVER_IPV6", "") or "").strip(),
	]
	endpoints: list[str] = []
	for raw_endpoint in endpoint_candidates:
		if not raw_endpoint:
			continue
		normalized = raw_endpoint.strip()
		if normalized.startswith("[") and normalized.endswith("]"):
			normalized = normalized[1:-1]
		if normalized and normalized not in endpoints:
			endpoints.append(normalized)

	form = EmailDiagnosticsForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		logs.append(f"[{timezone.now().isoformat()}] Starting email diagnostics run")
		logs.append(f"Email backend: {getattr(settings, 'EMAIL_BACKEND', '')}")
		logs.append(f"SMTP port: {getattr(settings, 'EMAIL_PORT', '')}")
		logs.append(f"TLS enabled: {getattr(settings, 'EMAIL_USE_TLS', False)}")
		logs.append(f"SMTP auth user: {getattr(settings, 'EMAIL_HOST_USER', '')}")
		logs.append(f"From address: {getattr(settings, 'DEFAULT_FROM_EMAIL', '')}")
		logs.append(f"Recipients: {', '.join(recipients)}")
		logs.append(f"Endpoint matrix: {', '.join(endpoints) if endpoints else '(none)'}")

		total_successes = 0
		for endpoint in endpoints:
			logs.append("-" * 60)
			logs.append(f"[Endpoint] {endpoint}")
			connection = get_connection(
				fail_silently=False,
				host=endpoint,
				port=int(getattr(settings, "EMAIL_PORT", 0) or 0),
				username=getattr(settings, "EMAIL_HOST_USER", ""),
				password=getattr(settings, "EMAIL_HOST_PASSWORD", ""),
				use_tls=bool(getattr(settings, "EMAIL_USE_TLS", False)),
			)
			logs.append("Created Django mail connection object")

			connection_open = False
			endpoint_status = "failed"
			try:
				open_result = connection.open()
				connection_open = True
				logs.append(f"connection.open() returned: {open_result}")
			except Exception as exc:
				logs.append(f"connection.open() failed: {exc.__class__.__name__}: {exc}")
				logs.append(traceback.format_exc())

			if connection_open:
				message = EmailMessage(
					subject=f"{form.cleaned_data['subject'].strip()} [{endpoint}]",
					body=(
						f"{form.cleaned_data['message'].strip()}\n\n"
						f"Endpoint under test: {endpoint}\n"
						f"Timestamp: {timezone.now().isoformat()}"
					),
					from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
					to=recipients,
					connection=connection,
				)
				message.extra_headers = {
					"X-Freeparty-Diagnostics": "smtp-test",
					"X-Freeparty-Diagnostics-At": timezone.now().isoformat(),
					"X-Freeparty-Diagnostics-Endpoint": endpoint,
				}
				try:
					sent_count = message.send(fail_silently=False)
					logs.append(f"Email send call returned: {sent_count}")
					endpoint_status = "success"
					total_successes += 1
				except Exception as exc:
					logs.append(f"Email send failed: {exc.__class__.__name__}: {exc}")
					logs.append(traceback.format_exc())
				finally:
					try:
						connection.close()
						logs.append("connection.close() completed")
					except Exception as exc:
						logs.append(f"connection.close() failed: {exc.__class__.__name__}: {exc}")

			endpoint_results.append({"endpoint": endpoint, "status": endpoint_status})

		if endpoints and total_successes == len(endpoints):
			result = "success"
			messages.success(request, "Email diagnostics completed successfully for all endpoints.")
		elif total_successes > 0:
			result = "partial"
			messages.warning(request, "Email diagnostics partially succeeded. Review endpoint matrix below.")
		else:
			result = "failed"
			messages.error(request, "Email diagnostics failed for all endpoints. Review verbose logs below.")

		if not endpoints:
			result = "failed"
			messages.error(request, "No SMTP endpoints configured. Set EMAIL_HOST or MAIL_SERVER_* values.")

	return render(
		request,
		"core/email_test.html",
		{
			"email_test_form": form,
			"email_test_logs": logs,
			"email_test_result": result,
			"email_test_recipients": recipients,
			"email_test_endpoints": endpoints,
			"email_test_endpoint_results": endpoint_results,
		},
	)


@require_http_methods(["GET"])
def me_redirect_view(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		return redirect("actors:detail", handle=request.user.actor.handle)
	return redirect("accounts:login")


@login_required
@require_http_methods(["GET"])
def inbox_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	section = request.GET.get("section", "all").strip().lower()
	if section not in {"all", "messages", "notifications"}:
		section = "all"
	mode = request.GET.get("mode", "summary").strip().lower()
	if mode not in {"summary", "activity"}:
		mode = "summary"
	filter_type = request.GET.get("filter", "all").strip().lower()
	if filter_type not in {"all", "unread"}:
		filter_type = "all"
	show_unread_only = filter_type == "unread"

	notifications_qs = Notification.objects.filter(recipient=actor).select_related("source_actor", "source_post")
	if show_unread_only:
		notifications_qs = notifications_qs.filter(read_at__isnull=True)
	notifications = list(notifications_qs[:5]) if section in {"all", "notifications"} else []

	pm_enabled = is_private_messages_enabled()
	conversations = []
	conversation_items = []
	if pm_enabled and section in {"all", "messages"}:
		conversation_items = populate_conversation_activity(
			actor=actor,
			conversations=get_conversation_queryset_for_actor(actor=actor),
		)
		if show_unread_only:
			conversation_items = [conversation for conversation in conversation_items if conversation.unread_message_count > 0]
		conversations = conversation_items[:5]

	activity_items = []
	if mode == "activity":
		if section in {"all", "notifications"}:
			for notification in notifications_qs:
				actor_label = ""
				if notification.source_actor_id:
					display_name = notification.source_actor.user.display_name if notification.source_actor and notification.source_actor.user else ""
					handle = notification.source_actor.handle if notification.source_actor else ""
					actor_label = f"{display_name} (@{handle})" if display_name else (f"@{handle}" if handle else "")

				post_snippet = ""
				if notification.source_post_id and notification.source_post:
					post_snippet = (notification.source_post.content or "").strip().replace("\n", " ")[:120]
					if len((notification.source_post.content or "").strip()) > 120:
						post_snippet += "..."

				summary_text = _notification_activity_summary(notification, actor_label)
				activity_items.append({
					"kind": "notification",
					"created_at": notification.created_at,
					"is_unread": notification.read_at is None,
					"title": notification.get_notification_type_display(),
					"summary": summary_text,
					"link_url": f"/posts/{notification.source_post_id}/" if notification.source_post_id else "/notifications/",
					"link_label": "Open related post" if notification.source_post_id else "Open notifications",
					"meta": f"{timezone.localtime(notification.created_at).strftime('%Y-%m-%d %H:%M')}",
					"actor_label": actor_label,
					"post_snippet": post_snippet,
				})

		if pm_enabled and section in {"all", "messages"}:
			latest_envelope_by_conversation_id = {}
			if conversation_items:
				latest_envelopes = (
					EncryptedMessageEnvelope.objects.filter(conversation__in=conversation_items)
					.select_related("sender", "sender__user")
					.order_by("conversation_id", "-created_at", "-id")
				)
				for envelope in latest_envelopes:
					if envelope.conversation_id not in latest_envelope_by_conversation_id:
						latest_envelope_by_conversation_id[envelope.conversation_id] = envelope

			for conversation in conversation_items:
				other_participant = next(
					(participant.actor for participant in conversation.participants.all() if participant.actor_id != actor.id),
					None,
				)
				other_name = "Unknown"
				if other_participant is not None:
					other_name = other_participant.user.display_name or f"@{other_participant.handle}"

				latest_envelope = latest_envelope_by_conversation_id.get(conversation.id)
				latest_sender_context = ""
				if latest_envelope is not None:
					if latest_envelope.sender_id == actor.id:
						latest_sender_context = "Latest envelope sent by you"
					elif latest_envelope.sender:
						sender_display_name = latest_envelope.sender.user.display_name if latest_envelope.sender.user else ""
						sender_handle = latest_envelope.sender.handle
						sender_label = f"{sender_display_name} (@{sender_handle})" if sender_display_name else f"@{sender_handle}"
						latest_sender_context = f"Latest envelope from {sender_label}"
					else:
						latest_sender_context = "Latest envelope sender unknown"

				activity_items.append({
					"kind": "message",
					"created_at": conversation.latest_message_created_at or conversation.updated_at,
					"is_unread": bool(conversation.unread_message_count),
					"title": f"Message thread with {other_name}",
					"summary": (
						f"{conversation.unread_message_count} unread · {conversation.total_message_count} encrypted envelope"
						f"{'s' if conversation.total_message_count != 1 else ''}"
					),
					"link_url": f"/messages/{conversation.id}/",
					"link_label": "Open conversation",
					"meta": f"{timezone.localtime(conversation.latest_message_created_at or conversation.updated_at).strftime('%Y-%m-%d %H:%M')}",
					"latest_sender_context": latest_sender_context,
				})

		activity_items.sort(key=lambda item: item["created_at"], reverse=True)

	query_parts = []
	if section != "all":
		query_parts.append(f"section={section}")
	if show_unread_only:
		query_parts.append("filter=unread")
	if mode != "summary":
		query_parts.append(f"mode={mode}")
	activity_query_string = "&".join(query_parts)
	activity_page_obj = paginate_queryset(request, activity_items, per_page=20, page_param="page") if mode == "activity" else None

	unread_notification_count = Notification.objects.filter(recipient=actor, read_at__isnull=True).count()
	unread_message_count = get_unread_conversation_count(actor=actor) if pm_enabled else 0
	query_string = f"?{activity_query_string}" if activity_query_string else ""

	return render(request, "core/inbox.html", {
		"section": section,
		"mode": mode,
		"filter_type": filter_type,
		"show_unread_only": show_unread_only,
		"pm_enabled": pm_enabled,
		"conversations": conversations,
		"notifications": notifications,
		"activity_items": list(activity_page_obj.object_list) if activity_page_obj else [],
		"activity_page_obj": activity_page_obj,
		"activity_query_string": activity_query_string,
		"unread_notification_count": unread_notification_count,
		"unread_message_count": unread_message_count,
		"query_string": query_string,
	})
