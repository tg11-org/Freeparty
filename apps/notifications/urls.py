from django.urls import path

from apps.notifications.views import mark_all_read_view, notifications_view

app_name = "notifications"

urlpatterns = [
    path("", notifications_view, name="list"),
    path("mark-all-read/", mark_all_read_view, name="mark-all-read"),
]
