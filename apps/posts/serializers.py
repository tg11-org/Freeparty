from rest_framework import serializers

from apps.posts.models import Post


class PostSerializer(serializers.ModelSerializer):
    author_handle = serializers.CharField(source="author.handle", read_only=True)

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["canonical_uri", "author"]
