from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.actors.api_views import ActorViewSet
from apps.core.api_views import api_live_view, api_ready_view
from apps.moderation.api_views import ModerationAttachmentViewSet, ModerationReportViewSet
from apps.notifications.api_views import NotificationViewSet
from apps.posts.api_views import CommentViewSet, PostViewSet
from apps.profiles.api_views import MyProfilePrivacyAPIView
from apps.social.api_views import FollowViewSet

router = DefaultRouter()
router.register("actors", ActorViewSet, basename="api-actors")
router.register("posts", PostViewSet, basename="api-posts")
router.register("comments", CommentViewSet, basename="api-comments")
router.register("follows", FollowViewSet, basename="api-follows")
router.register("notifications", NotificationViewSet, basename="api-notifications")
router.register("moderation/reports", ModerationReportViewSet, basename="api-moderation-reports")
router.register("moderation/attachments", ModerationAttachmentViewSet, basename="api-moderation-attachments")

urlpatterns = [
    path("health/live/", api_live_view, name="api-health-live"),
    path("health/ready/", api_ready_view, name="api-health-ready"),
    path("profiles/me/", MyProfilePrivacyAPIView.as_view(), name="api-profile-me"),
    path("", include(router.urls)),
]
