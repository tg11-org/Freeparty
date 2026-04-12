from rest_framework import permissions, viewsets

from apps.social.models import Follow
from apps.social.serializers import FollowSerializer


class FollowViewSet(viewsets.ModelViewSet):
    serializer_class = FollowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Follow.objects.filter(follower=self.request.user.actor).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(follower=self.request.user.actor, state=Follow.FollowState.ACCEPTED)
