from rest_framework import permissions, viewsets

from apps.actors.models import Actor
from apps.actors.serializers import ActorSerializer


class ActorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Actor.objects.all().order_by("-created_at")
    serializer_class = ActorSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "handle"
