from rest_framework import serializers

from apps.posts.models import Attachment, Comment, Post

_ALLOWED_MEDIA_TYPES = ("image/", "video/")
_MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MB


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = [
            "id",
            "attachment_type",
            "file",
            "alt_text",
            "caption",
            "mime_type",
            "file_size",
            "processing_state",
            "moderation_state",
        ]
        read_only_fields = [
            "id",
            "attachment_type",
            "mime_type",
            "file_size",
            "processing_state",
            "moderation_state",
        ]


class PostSerializer(serializers.ModelSerializer):
    author_handle = serializers.CharField(source="author.handle", read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "canonical_uri",
            "author",
            "author_handle",
            "content",
            "spoiler_text",
            "visibility",
            "in_reply_to",
            "thread_root",
            "quote_of",
            "attachments",
            "is_nsfw",
            "is_18plus",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["canonical_uri", "author"]


class CommentSerializer(serializers.ModelSerializer):
    author_handle = serializers.CharField(source="author.handle", read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "post",
            "author",
            "author_handle",
            "content",
            "is_edited",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["author", "is_edited"]
