from rest_framework import permissions, viewsets

from apps.core.services.uris import post_uri
from apps.posts.models import Post
from apps.posts.serializers import PostSerializer


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Post.objects.filter(deleted_at__isnull=True).select_related("author")
        if self.request.user.is_authenticated and hasattr(self.request.user, "actor"):
            return qs
        return qs.filter(visibility=Post.Visibility.PUBLIC)

    def perform_create(self, serializer):
        actor = self.request.user.actor
        post = serializer.save(author=actor, canonical_uri=post_uri("pending"))
        post.canonical_uri = post_uri(post.id)
        post.save(update_fields=["canonical_uri", "updated_at"])
