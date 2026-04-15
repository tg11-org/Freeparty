from django.contrib import admin

from apps.posts.models import Attachment, Comment, CommentEditHistory, Post, PostEditHistory


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


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


@admin.register(PostEditHistory)
class PostEditHistoryAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("post", "editor", "created_at")
	search_fields = ("post__id", "editor__username", "editor__email")
	readonly_fields = ("id", "post", "editor", "previous_content", "new_content", "created_at", "updated_at")


@admin.register(CommentEditHistory)
class CommentEditHistoryAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("comment", "editor", "created_at")
	search_fields = ("comment__id", "editor__username", "editor__email")
	readonly_fields = ("id", "comment", "editor", "previous_content", "new_content", "created_at", "updated_at")
