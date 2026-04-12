from django.contrib import admin

from apps.moderation.models import ModerationAction, ModerationNote, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ("id", "reporter", "reason", "status", "reviewed_by", "reviewed_at")
	list_filter = ("status",)
	search_fields = ("reason", "description", "reporter__handle")


admin.site.register(ModerationAction)
admin.site.register(ModerationNote)
