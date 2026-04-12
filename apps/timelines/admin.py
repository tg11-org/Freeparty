from django.contrib import admin

from apps.timelines.models import TimelineEntry


@admin.register(TimelineEntry)
class TimelineEntryAdmin(admin.ModelAdmin):
	list_display = ("owner", "post", "inserted_at")
	search_fields = ("owner__handle", "post__id")
