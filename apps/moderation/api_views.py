from datetime import datetime, time
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.moderation.models import ModerationAction, ModerationNote, Report
from apps.moderation.serializers import (
    CreateModerationActionSerializer,
    CreateModerationNoteSerializer,
    ReportDetailSerializer,
    ReportListSerializer,
    ReportStatusUpdateSerializer,
)


class ModerationReportViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        status_value = self.request.GET.get("status")
        reason = self.request.GET.get("reason", "").strip()
        actor_q = self.request.GET.get("actor", "").strip()
        post_q = self.request.GET.get("post", "").strip()
        target_type = self.request.GET.get("target", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()

        reports = Report.objects.select_related(
            "reporter",
            "target_actor",
            "target_post",
            "reviewed_by",
        ).prefetch_related("actions", "notes").order_by("-created_at")
        if status_value in {choice for choice, _ in Report.Status.choices}:
            reports = reports.filter(status=status_value)
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
        return reports

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ReportDetailSerializer
        return ReportListSerializer

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, pk=None):
        report = self.get_object()
        serializer = ReportStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report.status = serializer.validated_data["status"]
        report.reviewed_at = timezone.now()
        report.reviewed_by = request.user
        report.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

        return Response(ReportDetailSerializer(report).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="actions")
    def create_action(self, request, pk=None):
        report = self.get_object()
        serializer = CreateModerationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = ModerationAction.objects.create(
            report=report,
            actor_target=report.target_actor,
            post_target=report.target_post,
            moderator=request.user,
            action_type=serializer.validated_data["action_type"],
            notes=serializer.validated_data.get("notes", ""),
        )

        report.status = Report.Status.ACTIONED
        report.reviewed_at = timezone.now()
        report.reviewed_by = request.user
        report.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])

        return Response({"id": str(action.id)}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="notes")
    def create_note(self, request, pk=None):
        report = self.get_object()
        serializer = CreateModerationNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        note = ModerationNote.objects.create(
            report=report,
            author=request.user,
            body=serializer.validated_data["body"].strip(),
        )
        return Response({"id": str(note.id)}, status=status.HTTP_201_CREATED)
