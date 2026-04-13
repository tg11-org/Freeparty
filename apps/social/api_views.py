from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django.db.models import Q

from apps.core.permissions import can_follow_actor
from apps.social.models import Follow
from apps.social.serializers import FollowSerializer
from apps.social.services import approve_follow_request, follow_actor, reject_follow_request


class FollowViewSet(viewsets.ModelViewSet):
    serializer_class = FollowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        actor = self.request.user.actor
        if self.action == "list":
            return Follow.objects.filter(follower=actor).order_by("-created_at")
        return Follow.objects.filter(Q(follower=actor) | Q(followee=actor)).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        follower = request.user.actor
        followee = serializer.validated_data["followee"]
        if not can_follow_actor(follower, followee):
            raise PermissionDenied("Cannot follow this account.")
        follow = follow_actor(follower=follower, followee=followee)
        output = self.get_serializer(follow)
        return Response(output.data)

    @action(detail=False, methods=["get"], url_path="incoming")
    def incoming(self, request):
        qs = Follow.objects.filter(
            followee=request.user.actor,
            state=Follow.FollowState.PENDING,
        ).order_by("-created_at")
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        follow = self.get_object()
        if follow.followee_id != request.user.actor.id:
            raise PermissionDenied("Only the target account can approve requests.")
        if follow.state != Follow.FollowState.PENDING:
            raise PermissionDenied("Only pending requests can be approved.")
        follow = approve_follow_request(follow)
        return Response(self.get_serializer(follow).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        follow = self.get_object()
        if follow.followee_id != request.user.actor.id:
            raise PermissionDenied("Only the target account can reject requests.")
        if follow.state != Follow.FollowState.PENDING:
            raise PermissionDenied("Only pending requests can be rejected.")
        follow = reject_follow_request(follow)
        return Response(self.get_serializer(follow).data)

