from django.contrib import admin

from apps.moderation.models import ModerationAction, ModerationNote, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ("id", "reporter", "reason", "status", "reviewed_by", "reviewed_at")
	list_filter = ("status", "reason", "reviewed_by")
	search_fields = ("reason", "description", "reporter__handle", "target_actor__handle", "target_post__id")
	ordering = ("-created_at",)


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
	list_display = ("id", "action_type", "moderator", "report", "actor_target", "post_target", "applied_at")
	list_filter = ("action_type", "moderator")
	search_fields = ("notes", "report__id", "actor_target__handle", "post_target__id")
	ordering = ("-applied_at",)


@admin.register(ModerationNote)
class ModerationNoteAdmin(admin.ModelAdmin):
	list_display = ("id", "report", "author", "created_at")
	list_filter = ("author",)
	search_fields = ("body", "report__id", "author__username")
	ordering = ("-created_at",)
