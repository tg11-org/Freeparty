from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ("recipient", "notification_type", "read_at", "created_at")
	list_filter = ("notification_type", "read_at")
	search_fields = ("recipient__handle", "source_actor__handle")
