from django.contrib import admin

from apps.timelines.models import TimelineEntry


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(TimelineEntry)
class TimelineEntryAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("owner", "post", "inserted_at")
	search_fields = ("owner__handle", "post__id")
	readonly_fields = ("id", "owner", "post", "inserted_at")
