from django.urls import path

from apps.moderation.views import (
    moderation_attachment_state_view,
    moderation_dashboard_view,
    moderation_quick_status_view,
    moderation_report_detail_view,
    moderation_report_update_view,
    report_view,
)

app_name = "moderation"

urlpatterns = [
    path("", moderation_dashboard_view, name="dashboard"),
    path("report/", report_view, name="report"),
    path("reports/<uuid:report_id>/", moderation_report_detail_view, name="report-detail"),
    path("reports/<uuid:report_id>/update/", moderation_report_update_view, name="report-update"),
    path("reports/<uuid:report_id>/quick-status/", moderation_quick_status_view, name="quick-status"),
    path("attachments/<uuid:attachment_id>/state/", moderation_attachment_state_view, name="attachment-state"),
]
