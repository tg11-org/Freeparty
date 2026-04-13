from django.contrib import admin

from apps.posts.models import Attachment, Comment, Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
	list_display = ("id", "author", "visibility", "moderation_state", "created_at", "deleted_at")
	list_filter = ("visibility", "moderation_state", "local_only", "federated")
	search_fields = ("content", "author__handle", "canonical_uri")


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
	list_display = ("id", "post", "attachment_type", "mime_type", "processing_state", "moderation_state")
	list_filter = ("attachment_type", "processing_state", "moderation_state")
	search_fields = ("post__id", "mime_type")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
	list_display = ("id", "post", "author", "created_at", "deleted_at")
	list_filter = ("deleted_at",)
	search_fields = ("content", "author__handle")
