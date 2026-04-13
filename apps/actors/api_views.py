from rest_framework import permissions, viewsets
from django.db.models import Q

from apps.actors.models import Actor
from apps.social.models import Block, Follow
from apps.actors.serializers import ActorSerializer


class ActorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Actor.objects.filter(state=Actor.ActorState.ACTIVE).order_by("-created_at")
    serializer_class = ActorSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "handle"

    def get_queryset(self):
        qs = Actor.objects.filter(state=Actor.ActorState.ACTIVE).order_by("-created_at")
        if self.request.user.is_authenticated and hasattr(self.request.user, "actor"):
            viewer = self.request.user.actor
            followed_ids = Follow.objects.filter(
                follower=viewer,
                state=Follow.FollowState.ACCEPTED,
            ).values_list("followee_id", flat=True)
            blocked_by_me = Block.objects.filter(blocker=viewer).values_list("blocked_id", flat=True)
            blocked_me = Block.objects.filter(blocked=viewer).values_list("blocker_id", flat=True)
            return (
                qs.filter(Q(profile__is_private_account=False) | Q(id__in=followed_ids) | Q(id=viewer.id))
                .exclude(id__in=blocked_by_me)
                .exclude(id__in=blocked_me)
            )
        return qs.filter(profile__is_private_account=False)
