from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer

from apps.notifications.models import Notification


class NotificationSerializer(ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "payload",
            "source_actor",
            "source_post",
            "read_at",
            "created_at",
        ]


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        actor = getattr(self.request.user, "actor", None)
        if actor is None:
            return Notification.objects.none()
        queryset = Notification.objects.filter(recipient=actor).select_related("source_actor", "source_post")
        filter_type = self.request.GET.get("type", "all").strip()
        if filter_type == "unread":
            queryset = queryset.filter(read_at__isnull=True)
        elif filter_type in {choice[0] for choice in Notification.NotificationType.choices}:
            queryset = queryset.filter(notification_type=filter_type)
        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(self.get_serializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        actor = request.user.actor
        updated = Notification.objects.filter(recipient=actor, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": updated}, status=status.HTTP_200_OK)
