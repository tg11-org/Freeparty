from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.actors.api_views import ActorViewSet
from apps.core.api_views import api_live_view, api_ready_view
from apps.posts.api_views import PostViewSet
from apps.social.api_views import FollowViewSet

router = DefaultRouter()
router.register("actors", ActorViewSet, basename="api-actors")
router.register("posts", PostViewSet, basename="api-posts")
router.register("follows", FollowViewSet, basename="api-follows")

urlpatterns = [
    path("health/live/", api_live_view, name="api-health-live"),
    path("health/ready/", api_ready_view, name="api-health-ready"),
    path("", include(router.urls)),
]
