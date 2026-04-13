from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.core.permissions import (
    can_comment_on_post,
    can_delete_comment,
    can_delete_post,
    can_edit_comment,
    can_edit_post,
)
from apps.core.services.uris import post_uri
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_if_new, notify_mentions
from apps.posts.models import Attachment, Comment, CommentEditHistory, Post, PostEditHistory
from apps.posts.selectors import visible_public_posts_for_actor
from apps.posts.serializers import CommentSerializer, PostSerializer

_ALLOWED_MIME_PREFIXES = ("image/", "video/")
_MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if self.request.user.is_authenticated and hasattr(self.request.user, "actor"):
            actor = self.request.user.actor
            own_qs = Post.objects.filter(author=actor, deleted_at__isnull=True).select_related("author")
            public_qs = visible_public_posts_for_actor(actor=actor)
            qs = (own_qs | public_qs).distinct().order_by("-created_at")
        else:
            qs = visible_public_posts_for_actor(actor=None)

        tab = self.request.query_params.get("tab", "").strip().lower()
        if tab == "media":
            qs = qs.filter(
                attachments__attachment_type__in=["image", "video"],
                attachments__moderation_state="normal",
            ).distinct()

        return qs.prefetch_related("attachments")

    def perform_create(self, serializer):
        actor = self.request.user.actor
        post = serializer.save(author=actor, canonical_uri=post_uri("pending"))
        post.canonical_uri = post_uri(post.id)
        post.save(update_fields=["canonical_uri", "updated_at"])

        upload = self.request.FILES.get("attachment")
        if upload:
            content_type = getattr(upload, "content_type", "") or "application/octet-stream"
            if not any(content_type.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
                post.deleted_at = timezone.now()
                post.save(update_fields=["deleted_at", "updated_at"])
                raise ValidationError({"attachment": "Only image and video uploads are supported."})
            if upload.size > _MAX_ATTACHMENT_BYTES:
                post.deleted_at = timezone.now()
                post.save(update_fields=["deleted_at", "updated_at"])
                raise ValidationError({"attachment": "Attachment is too large (max 25 MB)."})
            attachment_type = (
                Attachment.AttachmentType.IMAGE
                if content_type.startswith("image/")
                else Attachment.AttachmentType.VIDEO
            )
            Attachment.objects.create(
                post=post,
                attachment_type=attachment_type,
                file=upload,
                alt_text=self.request.data.get("attachment_alt_text", ""),
                caption=self.request.data.get("attachment_caption", ""),
                mime_type=content_type,
                file_size=upload.size,
            )

        notify_mentions(content=post.content, source_actor=actor, source_post=post)

    def perform_update(self, serializer):
        post = self.get_object()
        if not can_edit_post(self.request.user.actor, post):
            raise PermissionDenied("You can only edit your own posts.")
        previous_content = post.content
        previous_spoiler_text = post.spoiler_text
        previous_visibility = post.visibility
        updated = serializer.save()
        if (
            previous_content != updated.content
            or previous_spoiler_text != updated.spoiler_text
            or previous_visibility != updated.visibility
        ):
            PostEditHistory.objects.create(
                post=updated,
                editor=self.request.user,
                previous_content=previous_content,
                new_content=updated.content,
                previous_spoiler_text=previous_spoiler_text,
                new_spoiler_text=updated.spoiler_text,
                previous_visibility=previous_visibility,
                new_visibility=updated.visibility,
            )

    def perform_destroy(self, instance):
        if not can_delete_post(self.request.user.actor, instance):
            raise PermissionDenied("You can only delete your own posts.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at", "updated_at"])


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Comment.objects.filter(deleted_at__isnull=True).select_related("author", "post", "post__author")
        post_id = self.request.query_params.get("post")
        if post_id:
            qs = qs.filter(post_id=post_id)
        return qs.order_by("created_at")

    def perform_create(self, serializer):
        actor = self.request.user.actor
        post = serializer.validated_data["post"]
        if not can_comment_on_post(actor, post):
            raise PermissionDenied("You cannot comment on this post.")
        comment = serializer.save(author=actor)
        if post.author != actor:
            create_notification_if_new(
                recipient=post.author,
                source_actor=actor,
                notification_type=Notification.NotificationType.REPLY,
                source_post=post,
            )
        notify_mentions(content=comment.content, source_actor=actor, source_post=post)

    def perform_update(self, serializer):
        comment = self.get_object()
        if not can_edit_comment(self.request.user.actor, comment):
            raise PermissionDenied("You can only edit your own comments.")
        previous_content = comment.content
        updated = serializer.save(is_edited=True)
        if previous_content != updated.content:
            CommentEditHistory.objects.create(
                comment=updated,
                editor=self.request.user,
                previous_content=previous_content,
                new_content=updated.content,
            )

    def perform_destroy(self, instance):
        if not can_delete_comment(self.request.user.actor, instance):
            raise PermissionDenied("You can only delete your own comments.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at", "updated_at"])
