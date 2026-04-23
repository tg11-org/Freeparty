from datetime import datetime, time
from statistics import median
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, DateTimeField, F, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from apps.actors.models import Actor
from apps.moderation.models import ModerationAction, ModerationNote, Report
from apps.posts.models import Attachment, Post


def _build_report_context(*, target_actor=None, target_post=None, selected_reason: str = "", description: str = "") -> dict:
	severity_by_reason = {
		value: Report.severity_for_reason(value)
		for value, _label in Report.Reason.choices
	}
	return {
		"target_actor": target_actor,
		"target_post": target_post,
		"reason_choices": Report.Reason.choices,
		"selected_reason": Report.normalize_reason(selected_reason),
		"description": description,
		"severity_preview": Report.severity_for_reason(selected_reason),
		"severity_by_reason": severity_by_reason,
	}


@login_required
@require_http_methods(["GET", "POST"])
def report_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	target_actor_id = request.POST.get("target_actor_id") or request.GET.get("target_actor_id")
	target_post_id = request.POST.get("target_post_id") or request.GET.get("target_post_id")
	reason = request.POST.get("reason", Report.Reason.OTHER)
	description = request.POST.get("description", "")

	target_actor = Actor.objects.filter(id=target_actor_id).first() if target_actor_id else None
	target_post = Post.objects.filter(id=target_post_id).first() if target_post_id else None

	if not target_actor and not target_post:
		messages.error(request, "Please choose a report target.")
		return redirect("home")

	if request.method == "GET":
		return render(request, "moderation/report_form.html", _build_report_context(target_actor=target_actor, target_post=target_post))

	normalized_reason = Report.normalize_reason(reason)
	severity = Report.severity_for_reason(normalized_reason)

	Report.objects.create(
		reporter=actor,
		target_actor=target_actor,
		target_post=target_post,
		reason=normalized_reason,
		severity=severity,
		description=description,
	)
	messages.success(request, "Report submitted.")
	return redirect("home")


@login_required
def moderation_dashboard_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	status_param = request.GET.get("status")
	status = Report.Status.OPEN if status_param is None else status_param.strip()
	severity = request.GET.get("severity", "").strip()
	reason_category = request.GET.get("reason_category", "").strip()
	reason = request.GET.get("reason", "").strip()
	actor_q = request.GET.get("actor", "").strip()
	post_q = request.GET.get("post", "").strip()
	target_type = request.GET.get("target", "").strip()
	owner_state = request.GET.get("owner_state", "").strip()
	sla_breached = request.GET.get("sla_breached", "").strip().lower()
	date_from = request.GET.get("date_from", "").strip()
	date_to = request.GET.get("date_to", "").strip()
	reports = Report.objects.select_related("reporter", "target_actor", "target_post", "reviewed_by").order_by("-created_at")
	if status in {choice for choice, _ in Report.Status.choices}:
		reports = reports.filter(status=status)
	if severity in {choice for choice, _ in Report.Severity.choices}:
		reports = reports.filter(severity=severity)
	if reason_category in {choice for choice, _ in Report.Reason.choices}:
		reports = reports.filter(reason=reason_category)
	if reason:
		reports = reports.filter(reason__icontains=reason)
	if actor_q:
		reports = reports.filter(reporter__handle__icontains=actor_q)
	if post_q:
		try:
			reports = reports.filter(target_post_id=UUID(post_q))
		except ValueError:
			reports = reports.none()

	parsed_from = parse_date(date_from) if date_from else None
	if parsed_from:
		start_of_day = timezone.make_aware(datetime.combine(parsed_from, time.min), timezone.get_current_timezone())
		reports = reports.filter(created_at__gte=start_of_day)

	parsed_to = parse_date(date_to) if date_to else None
	if parsed_to:
		end_of_day = timezone.make_aware(datetime.combine(parsed_to, time.max), timezone.get_current_timezone())
		reports = reports.filter(created_at__lte=end_of_day)

	if target_type == "actor":
		reports = reports.filter(target_actor__isnull=False)
	elif target_type == "post":
		reports = reports.filter(target_post__isnull=False)
	if owner_state == "assigned":
		reports = reports.filter(assigned_to__isnull=False)
	elif owner_state == "unassigned":
		reports = reports.filter(assigned_to__isnull=True)
	if sla_breached == "true":
		now = timezone.now()
		reports = (
			reports.filter(responded_at__isnull=True, sla_target_minutes__gt=0)
			.annotate(sla_anchor=Coalesce("first_assigned_at", "created_at"))
			.annotate(
				sla_deadline=Case(
					When(severity=Report.Severity.CRITICAL, then=F("sla_anchor") + Value(timezone.timedelta(minutes=30))),
					When(severity=Report.Severity.HIGH, then=F("sla_anchor") + Value(timezone.timedelta(hours=2))),
					When(severity=Report.Severity.MEDIUM, then=F("sla_anchor") + Value(timezone.timedelta(hours=8))),
					When(severity=Report.Severity.LOW, then=F("sla_anchor") + Value(timezone.timedelta(hours=24))),
					default=F("sla_anchor") + Value(timezone.timedelta(hours=8)),
					output_field=DateTimeField(),
				)
			)
			.filter(sla_deadline__lt=now)
		)

	return render(request, "moderation/dashboard.html", {
		"reports": reports,
		"selected_status": status,
		"selected_severity": severity,
		"selected_reason_category": reason_category,
		"severity_choices": Report.Severity.choices,
		"reason_choices": Report.Reason.choices,
		"reason": reason,
		"actor_q": actor_q,
		"post_q": post_q,
		"target_type": target_type,
		"owner_state": owner_state,
		"sla_breached": sla_breached,
		"date_from": date_from,
		"date_to": date_to,
	})


@login_required
def moderation_report_detail_view(request: HttpRequest, report_id: str) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	report = get_object_or_404(
		Report.objects.select_related("reporter", "target_actor", "target_post", "target_post__author", "reviewed_by").prefetch_related("actions", "notes"),
		id=report_id,
	)
	reportee = report.target_actor or (report.target_post.author if report.target_post else None)
	attachments = report.target_post.attachments.all().order_by("created_at") if report.target_post else []
	return render(
		request,
		"moderation/report_detail.html",
		{
			"report": report,
			"reportee": reportee,
			"attachments": attachments,
			"action_choices": ModerationAction.ActionType.choices,
		},
	)


@login_required
@require_POST
def moderation_report_update_view(request: HttpRequest, report_id: str) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	report = get_object_or_404(Report, id=report_id)
	new_status = request.POST.get("status")
	action_type = request.POST.get("action_type")
	notes = request.POST.get("notes", "")
	internal_note = request.POST.get("internal_note", "")
	assigned_to = request.POST.get("assigned_to", "").strip()

	if assigned_to:
		from apps.accounts.models import User

		report.assigned_to = User.objects.filter(id=assigned_to, is_staff=True).first()
		if report.assigned_to and report.first_assigned_at is None:
			report.first_assigned_at = timezone.now()

	if new_status and report.severity in {Report.Severity.HIGH, Report.Severity.CRITICAL}:
		if not report.evidence_hash and not notes.strip() and not internal_note.strip():
			messages.error(request, "High-severity reports require evidence notes before status changes.")
			return redirect("moderation:report-detail", report_id=report.id)

	if new_status in {choice for choice, _ in Report.Status.choices}:
		if notes.strip() or internal_note.strip():
			report.stamp_evidence_hash(report.description, notes, internal_note)
		report.status = new_status
		report.reviewed_at = timezone.now()
		report.reviewed_by = request.user
		if report.responded_at is None:
			report.responded_at = timezone.now()
		report.save(update_fields=["status", "reviewed_at", "reviewed_by", "assigned_to", "first_assigned_at", "responded_at", "evidence_hash", "updated_at"])

	if action_type in {choice for choice, _ in ModerationAction.ActionType.choices}:
		if notes.strip() or internal_note.strip():
			report.stamp_evidence_hash(report.description, notes, internal_note)
		ModerationAction.objects.create(
			report=report,
			actor_target=report.target_actor,
			post_target=report.target_post,
			moderator=request.user,
			action_type=action_type,
			notes=notes,
		)
		if not new_status:
			report.status = Report.Status.ACTIONED
			report.reviewed_at = timezone.now()
			report.reviewed_by = request.user
			if report.responded_at is None:
				report.responded_at = timezone.now()
			report.save(update_fields=["status", "reviewed_at", "reviewed_by", "responded_at", "evidence_hash", "updated_at"])

	if internal_note.strip():
		ModerationNote.objects.create(report=report, author=request.user, body=internal_note.strip())

	messages.success(request, "Moderation update saved.")
	return redirect("moderation:report-detail", report_id=report.id)


@login_required
def moderation_sla_analytics_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	severity = request.GET.get("severity", "").strip()
	reports = Report.objects.exclude(first_assigned_at__isnull=True)
	if severity in {choice for choice, _ in Report.Severity.choices}:
		reports = reports.filter(severity=severity)

	completed = [
		int((report.responded_at - report.first_assigned_at).total_seconds() / 60)
		for report in reports
		if report.responded_at and report.first_assigned_at
	]
	sorted_minutes = sorted(completed)
	p50 = median(sorted_minutes) if sorted_minutes else 0
	p95_index = int(len(sorted_minutes) * 0.95) - 1 if sorted_minutes else -1
	p95 = sorted_minutes[max(p95_index, 0)] if sorted_minutes else 0
	breached = sum(1 for report in reports if report.sla_breached())
	return JsonResponse(
		{
			"severity": severity or "all",
			"completed_count": len(sorted_minutes),
			"p50_response_minutes": p50,
			"p95_response_minutes": p95,
			"sla_breached_count": breached,
		}
	)


@login_required
@require_POST
def moderation_quick_status_view(request: HttpRequest, report_id: str) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	report = get_object_or_404(Report, id=report_id)
	new_status = request.POST.get("status")
	if new_status in {choice for choice, _ in Report.Status.choices}:
		report.status = new_status
		report.reviewed_at = timezone.now()
		report.reviewed_by = request.user
		report.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])
		messages.success(request, f"Report moved to {new_status}.")
	else:
		messages.error(request, "Invalid status value.")
	return redirect("moderation:dashboard")


@login_required
@require_POST
def moderation_attachment_state_view(request: HttpRequest, attachment_id: str) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	attachment = get_object_or_404(Attachment.objects.select_related("post"), id=attachment_id)
	new_state = request.POST.get("moderation_state", "").strip().lower()
	report_id = request.POST.get("report_id", "").strip()
	notes = request.POST.get("notes", "").strip()

	valid_states = {
		Attachment.ModerationState.NORMAL,
		Attachment.ModerationState.FLAGGED,
		Attachment.ModerationState.REMOVED,
	}
	if new_state not in valid_states:
		messages.error(request, "Invalid attachment moderation state.")
		if report_id:
			return redirect("moderation:report-detail", report_id=report_id)
		return redirect("moderation:dashboard")

	attachment.moderation_state = new_state
	attachment.save(update_fields=["moderation_state", "updated_at"])

	action_type = (
		ModerationAction.ActionType.POST_REMOVE
		if new_state == Attachment.ModerationState.REMOVED
		else ModerationAction.ActionType.POST_HIDE
	)
	ModerationAction.objects.create(
		post_target=attachment.post,
		moderator=request.user,
		action_type=action_type,
		notes=f"attachment_id={attachment.id}; state={new_state}; notes={notes}".strip(),
	)
	messages.success(request, f"Attachment state updated to {new_state}.")

	if report_id:
		return redirect("moderation:report-detail", report_id=report_id)
	return redirect("moderation:dashboard")
