from django.urls import path

from apps.core.views import health_live_view, health_ready_view, health_status_view, home_view, me_redirect_view

urlpatterns = [
    path("", home_view, name="home"),
    path("health/", health_status_view, name="health-status"),
    path("health/live/", health_live_view, name="health-live"),
    path("health/ready/", health_ready_view, name="health-ready"),
    path("me/", me_redirect_view, name="me"),
]
