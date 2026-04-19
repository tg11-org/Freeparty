from django.urls import path

from apps.core.views import (
    about_view,
    changelog_view,
    email_test_view,
    faq_view,
    guidelines_view,
    health_live_view,
    health_ready_view,
    health_status_view,
    home_view,
    inbox_view,
    me_redirect_view,
    privacy_view,
    support_view,
    terms_view,
)

urlpatterns = [
    path("", home_view, name="home"),
    path("health/", health_status_view, name="health-status"),
    path("health/live/", health_live_view, name="health-live"),
    path("health/ready/", health_ready_view, name="health-ready"),
    path("about/", about_view, name="about"),
    path("terms/", terms_view, name="terms"),
    path("privacy/", privacy_view, name="privacy"),
    path("guidelines/", guidelines_view, name="guidelines"),
    path("faq/", faq_view, name="faq"),
    path("support/", support_view, name="support"),
    path("support/email-test/", email_test_view, name="email-test"),
    path("changelog/", changelog_view, name="changelog"),
    path("inbox/", inbox_view, name="inbox"),
    path("me/", me_redirect_view, name="me"),
]
