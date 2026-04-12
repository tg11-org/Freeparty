from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.actors.models import Actor
from apps.moderation.models import ModerationAction, ModerationNote, Report
from apps.posts.models import Post


@login_required
@require_POST
def report_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor
	target_actor_id = request.POST.get("target_actor_id")
	target_post_id = request.POST.get("target_post_id")
	reason = request.POST.get("reason", "unspecified")
	description = request.POST.get("description", "")

	target_actor = Actor.objects.filter(id=target_actor_id).first() if target_actor_id else None
	target_post = Post.objects.filter(id=target_post_id).first() if target_post_id else None

	if not target_actor and not target_post:
		messages.error(request, "Please choose a report target.")
		return redirect("home")

	Report.objects.create(
		reporter=actor,
		target_actor=target_actor,
		target_post=target_post,
		reason=reason,
		description=description,
	)
	messages.success(request, "Report submitted.")
	return redirect("home")


@login_required
def moderation_dashboard_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	status = request.GET.get("status")
	reports = Report.objects.select_related("reporter", "target_actor", "target_post", "reviewed_by").order_by("-created_at")
	if status in {Report.Status.OPEN, Report.Status.REVIEWING, Report.Status.RESOLVED, Report.Status.DISMISSED}:
		reports = reports.filter(status=status)

	return render(request, "moderation/dashboard.html", {"reports": reports, "selected_status": status})


@login_required
def moderation_report_detail_view(request: HttpRequest, report_id: str) -> HttpResponse:
	if not request.user.is_staff:
		messages.error(request, "Moderator access required.")
		return redirect("home")

	report = get_object_or_404(
		Report.objects.select_related("reporter", "target_actor", "target_post", "reviewed_by").prefetch_related("actions", "notes"),
		id=report_id,
	)
	return render(request, "moderation/report_detail.html", {"report": report, "action_choices": ModerationAction.ActionType.choices})


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

	if new_status in {choice for choice, _ in Report.Status.choices}:
		report.status = new_status
		report.reviewed_at = timezone.now()
		report.reviewed_by = request.user
		report.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

	if action_type in {choice for choice, _ in ModerationAction.ActionType.choices}:
		ModerationAction.objects.create(
			report=report,
			actor_target=report.target_actor,
			post_target=report.target_post,
			moderator=request.user,
			action_type=action_type,
			notes=notes,
		)

	if internal_note.strip():
		ModerationNote.objects.create(report=report, author=request.user, body=internal_note.strip())

	messages.success(request, "Moderation update saved.")
	return redirect("moderation:report-detail", report_id=report.id)
