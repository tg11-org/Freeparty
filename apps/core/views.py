from urllib.parse import urlencode
import traceback
import csv
import json
from datetime import datetime, time

from django.conf import settings
from django.contrib import messages
from django.core.checks import run_checks
from django.core.cache import cache
from django.core.mail import EmailMessage, get_connection
from django.db import connections
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from apps.core.forms import EmailDiagnosticsForm, SupportRequestForm
from apps.core.health_access import is_ready_endpoint_authorized
from apps.core.pagination import paginate_queryset
from apps.core.permissions import (
	can_run_email_diagnostics,
	can_view_security_audit_events,
	can_view_security_posture,
	can_view_security_triage,
)
from apps.notifications.models import Notification
from apps.accounts.models import RecoveryCode, TOTPDevice, User
from apps.moderation.models import Report, SecurityAuditEvent, TrustSignal
from apps.private_messages.models import EncryptedMessageEnvelope
from apps.private_messages.services import (
	get_conversation_queryset_for_actor,
	get_unread_conversation_count,
	is_private_messages_enabled,
	populate_conversation_activity,
)
from apps.social.models import Bookmark, Dislike, HiddenPost, Like, Repost
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
		disliked_ids = set()
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
		disliked_ids = set(Dislike.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		hidden_ids = set(HiddenPost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	else:
		bookmarked_ids = set()
		hidden_ids = set()
		disliked_ids = set()
	return render(request, "core/home.html", {
		"posts": posts,
		"page_obj": page_obj,
		"liked_ids": liked_ids,
		"disliked_ids": disliked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"hidden_ids": hidden_ids,
		"active_tab": active_tab,
		"query_string": f"tab={active_tab}" if active_tab != "all" else "",
	})


@require_http_methods(["GET"])
def health_live_view(request: HttpRequest) -> JsonResponse:
	return JsonResponse({"status": "ok", "service": "freeparty", "check": "live"}, status=200)


@require_http_methods(["GET"])
def health_ready_view(request: HttpRequest) -> JsonResponse:
	if not is_ready_endpoint_authorized(request):
		return JsonResponse({"detail": "Not found."}, status=404)

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
@require_http_methods(["GET"])
def security_posture_view(request: HttpRequest) -> HttpResponse:
	if not can_view_security_posture(request.user):
		return HttpResponseForbidden("Security posture access required.")

	date_from_raw = (request.GET.get("date_from") or "").strip()
	date_to_raw = (request.GET.get("date_to") or "").strip()
	parsed_from = parse_date(date_from_raw) if date_from_raw else None
	parsed_to = parse_date(date_to_raw) if date_to_raw else None
	if parsed_from is None or parsed_to is None:
		parsed_to = timezone.localdate()
		parsed_from = parsed_to - timezone.timedelta(days=6)

	range_start = timezone.make_aware(datetime.combine(parsed_from, time.min), timezone.get_current_timezone())
	range_end = timezone.make_aware(datetime.combine(parsed_to, time.max), timezone.get_current_timezone())

	security_errors = run_checks(tags=["security"], include_deployment_checks=True)
	guardrail_errors = [error for error in security_errors if getattr(error, "id", "").startswith("core.E")]

	health_public = bool(getattr(settings, "HEALTH_READY_PUBLIC", True))
	csp_mode = str(getattr(settings, "CSP_ROLLOUT_MODE", "legacy-report-only") or "legacy-report-only")

	checks = [
		{
			"label": "DEBUG disabled",
			"value": not bool(getattr(settings, "DEBUG", False)),
			"status": "ok" if not bool(getattr(settings, "DEBUG", False)) else "warn",
			"hint": "Set DEBUG=False in production.",
		},
		{
			"label": "SSL redirect enabled",
			"value": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
			"status": "ok" if bool(getattr(settings, "SECURE_SSL_REDIRECT", False)) else "warn",
			"hint": "Enable SECURE_SSL_REDIRECT in production.",
		},
		{
			"label": "Secure cookies",
			"value": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) and bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
			"status": "ok" if bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) and bool(getattr(settings, "CSRF_COOKIE_SECURE", False)) else "warn",
			"hint": "Set SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE=True.",
		},
		{
			"label": "CSP rollout mode",
			"value": csp_mode,
			"status": "ok" if csp_mode in {"strict-report-only", "strict-enforce"} else "info",
			"hint": "Use strict-report-only, then strict-enforce after cleanup.",
		},
		{
			"label": "Readiness endpoint public",
			"value": health_public,
			"status": "warn" if health_public else "ok",
			"hint": "Set HEALTH_READY_PUBLIC=False in production.",
		},
		{
			"label": "Readiness token configured",
			"value": bool(str(getattr(settings, "HEALTH_READY_TOKEN", "") or "").strip()),
			"status": "ok" if bool(str(getattr(settings, "HEALTH_READY_TOKEN", "") or "").strip()) else "info",
			"hint": "Set HEALTH_READY_TOKEN for non-public probes.",
		},
	]

	audit_by_day = {label: 0 for label in [(parsed_from + timezone.timedelta(days=offset)).isoformat() for offset in range((parsed_to - parsed_from).days + 1)]}
	for row in (
		SecurityAuditEvent.objects.filter(created_at__gte=range_start, created_at__lte=range_end)
		.annotate(day=TruncDate("created_at"))
		.values("day")
		.annotate(count=Count("id"))
	):
		day_label = str(row.get("day"))
		if day_label in audit_by_day:
			audit_by_day[day_label] = row.get("count", 0)

	reports_by_status = {
		row["status"]: row["count"]
		for row in (
			Report.objects.filter(created_at__gte=range_start, created_at__lte=range_end)
			.values("status")
			.annotate(count=Count("id"))
		)
	}

	max_audit = max(audit_by_day.values()) if audit_by_day else 0
	audit_chart = [
		{
			"label": label,
			"count": count,
			"pct": int((count / max_audit) * 100) if max_audit else 0,
		}
		for label, count in audit_by_day.items()
	]

	return render(
		request,
		"core/security_posture.html",
		{
			"posture_checks": checks,
			"security_error_count": len(security_errors),
			"guardrail_error_count": len(guardrail_errors),
			"guardrail_errors": guardrail_errors,
			"csp_enforce_enabled": bool(getattr(settings, "CSP_ENFORCE_ENABLED", False)),
			"csp_report_only_enabled": bool(getattr(settings, "CSP_REPORT_ONLY_ENABLED", False)),
			"health_ready_public": health_public,
			"health_ready_allow_staff": bool(getattr(settings, "HEALTH_READY_ALLOW_STAFF", True)),
			"health_ready_allowed_ips": list(getattr(settings, "HEALTH_READY_ALLOWED_IPS", []) or []),
			"allowed_hosts": list(getattr(settings, "ALLOWED_HOSTS", []) or []),
			"csrf_trusted_origins": list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []),
			"csp_rollout_mode": csp_mode,
			"date_from": parsed_from.isoformat(),
			"date_to": parsed_to.isoformat(),
			"audit_chart": audit_chart,
			"reports_by_status": reports_by_status,
		},
	)


@login_required
@require_http_methods(["GET"])
def auth_forensics_view(request: HttpRequest) -> HttpResponse:
	if not can_view_security_audit_events(request.user):
		return HttpResponseForbidden("Security audit access required.")

	date_from_raw = (request.GET.get("date_from") or "").strip()
	date_to_raw = (request.GET.get("date_to") or "").strip()
	parsed_from = parse_date(date_from_raw) if date_from_raw else None
	parsed_to = parse_date(date_to_raw) if date_to_raw else None
	if parsed_from is None or parsed_to is None:
		parsed_to = timezone.localdate()
		parsed_from = parsed_to - timezone.timedelta(days=6)

	range_start = timezone.make_aware(datetime.combine(parsed_from, time.min), timezone.get_current_timezone())
	range_end = timezone.make_aware(datetime.combine(parsed_to, time.max), timezone.get_current_timezone())

	recent_events = list(
		SecurityAuditEvent.objects.select_related("user")
		.filter(created_at__gte=range_start, created_at__lte=range_end)
		.order_by("-created_at")[:200]
	)

	counts_by_type = {
		entry["event_type"]: entry["count"]
		for entry in (
			SecurityAuditEvent.objects.filter(created_at__gte=range_start, created_at__lte=range_end)
			.values("event_type")
			.annotate(count=Count("id"))
		)
	}

	users_with_failures = list(
		User.objects.filter(audit_events__event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE, audit_events__created_at__gte=range_start, audit_events__created_at__lte=range_end)
		.annotate(login_failure_count=Count("audit_events", filter=Q(audit_events__event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE, audit_events__created_at__gte=range_start, audit_events__created_at__lte=range_end), distinct=True))
		.order_by("-login_failure_count", "username")[:20]
	)

	verified_totp_count = TOTPDevice.objects.filter(verified=True).count()
	recent_recovery_code_use_count = RecoveryCode.objects.filter(used_at__gte=range_start, used_at__lte=range_end).count()

	export_format = (request.GET.get("format") or "").strip().lower()
	if export_format == "json":
		payload = [
			{
				"created_at": event.created_at.isoformat(),
				"event_type": event.event_type,
				"user_id": str(event.user_id),
				"username": event.user.username,
				"email": event.user.email,
				"ip_address": event.ip_address,
				"details": event.details,
			}
			for event in recent_events
		]
		return HttpResponse(
			json.dumps(payload, indent=2),
			content_type="application/json",
			headers={"Content-Disposition": f"attachment; filename=auth-forensics-{parsed_from.isoformat()}-to-{parsed_to.isoformat()}.json"},
		)
	if export_format == "csv":
		response = HttpResponse(content_type="text/csv")
		response["Content-Disposition"] = f"attachment; filename=auth-forensics-{parsed_from.isoformat()}-to-{parsed_to.isoformat()}.csv"
		writer = csv.writer(response)
		writer.writerow(["created_at", "event_type", "user_id", "username", "email", "ip_address", "details"])
		for event in recent_events:
			writer.writerow([
				event.created_at.isoformat(),
				event.event_type,
				str(event.user_id),
				event.user.username,
				event.user.email,
				event.ip_address or "",
				json.dumps(event.details or {}, separators=(",", ":")),
			])
		return response

	failures_by_day = {label: 0 for label in [(parsed_from + timezone.timedelta(days=offset)).isoformat() for offset in range((parsed_to - parsed_from).days + 1)]}
	for row in (
		SecurityAuditEvent.objects.filter(
			created_at__gte=range_start,
			created_at__lte=range_end,
			event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE,
		)
		.annotate(day=TruncDate("created_at"))
		.values("day")
		.annotate(count=Count("id"))
	):
		day_label = str(row.get("day"))
		if day_label in failures_by_day:
			failures_by_day[day_label] = row.get("count", 0)

	max_failures = max(failures_by_day.values()) if failures_by_day else 0
	failure_chart = [
		{
			"label": label,
			"count": count,
			"pct": int((count / max_failures) * 100) if max_failures else 0,
		}
		for label, count in failures_by_day.items()
	]

	return render(
		request,
		"core/auth_forensics.html",
		{
			"window_start": range_start,
			"recent_events": recent_events,
			"counts_by_type": counts_by_type,
			"users_with_failures": users_with_failures,
			"verified_totp_count": verified_totp_count,
			"recent_recovery_code_use_count": recent_recovery_code_use_count,
			"date_from": parsed_from.isoformat(),
			"date_to": parsed_to.isoformat(),
			"failure_chart": failure_chart,
		},
	)


@login_required
@require_http_methods(["GET"])
def security_triage_view(request: HttpRequest) -> HttpResponse:
	if not can_view_security_triage(request.user):
		return HttpResponseForbidden("Security triage access required.")

	date_from_raw = (request.GET.get("date_from") or "").strip()
	date_to_raw = (request.GET.get("date_to") or "").strip()
	parsed_from = parse_date(date_from_raw) if date_from_raw else None
	parsed_to = parse_date(date_to_raw) if date_to_raw else None
	if parsed_from is None or parsed_to is None:
		parsed_to = timezone.localdate()
		parsed_from = parsed_to - timezone.timedelta(days=6)

	range_start = timezone.make_aware(datetime.combine(parsed_from, time.min), timezone.get_current_timezone())
	range_end = timezone.make_aware(datetime.combine(parsed_to, time.max), timezone.get_current_timezone())

	high_risk_reports = (
		Report.objects.select_related("reporter", "target_actor", "target_post")
		.filter(
			status__in=[Report.Status.OPEN, Report.Status.UNDER_REVIEW],
			severity__in=[Report.Severity.HIGH, Report.Severity.CRITICAL],
			created_at__gte=range_start,
			created_at__lte=range_end,
		)
		.order_by("-created_at")[:20]
	)

	throttled_signals = (
		TrustSignal.objects.select_related("actor", "actor__user")
		.filter(is_throttled=True)
		.order_by("trust_score", "-last_computed_at")[:20]
	)

	failed_login_accounts = (
		User.objects.filter(
			audit_events__event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE,
			audit_events__created_at__gte=range_start,
			audit_events__created_at__lte=range_end,
		)
		.annotate(
			login_failure_count=Count(
				"audit_events",
				filter=Q(
					audit_events__event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE,
					audit_events__created_at__gte=range_start,
					audit_events__created_at__lte=range_end,
				),
				distinct=True,
			)
		)
		.order_by("-login_failure_count", "username")[:20]
	)

	return render(
		request,
		"core/security_triage.html",
		{
			"date_from": parsed_from.isoformat(),
			"date_to": parsed_to.isoformat(),
			"high_risk_reports": high_risk_reports,
			"throttled_signals": throttled_signals,
			"failed_login_accounts": failed_login_accounts,
		},
	)


@login_required
@require_http_methods(["GET", "POST"])
def email_test_view(request: HttpRequest) -> HttpResponse:
	if not can_run_email_diagnostics(request.user):
		return HttpResponseForbidden("Email diagnostics access required.")

	recipients = list(getattr(settings, "EMAIL_DIAGNOSTIC_RECIPIENTS", []) or [])
	if not recipients and request.user.email:
		recipients = [request.user.email]
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
