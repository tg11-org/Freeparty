from django.contrib import admin

from apps.notifications.models import Notification


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(Notification)
class NotificationAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("recipient", "notification_type", "read_at", "created_at")
	list_filter = ("notification_type", "read_at")
	search_fields = ("recipient__handle", "source_actor__handle")
	readonly_fields = (
		"id",
		"recipient",
		"source_actor",
		"source_post",
		"notification_type",
		"payload",
		"read_at",
		"created_at",
	)
