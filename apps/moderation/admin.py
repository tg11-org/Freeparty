from django.contrib import admin

from apps.moderation.models import ModerationAction, ModerationNote, Report, SecurityAuditEvent, TrustSignal


class ImmutableAdminMixin:
	"""Use for event-style records that should never be edited manually."""

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ("id", "reporter", "reason", "status", "reviewed_by", "reviewed_at")
	list_filter = ("status", "reason", "reviewed_by")
	search_fields = ("reason", "description", "reporter__handle", "target_actor__handle", "target_post__id")
	ordering = ("-created_at",)
	readonly_fields = ("id", "reporter", "target_actor", "target_post", "reason", "severity", "description", "created_at", "updated_at")
	fields = (
		"id",
		"reporter",
		"target_actor",
		"target_post",
		"reason",
		"severity",
		"description",
		"status",
		"reviewed_by",
		"reviewed_at",
		"created_at",
		"updated_at",
	)


@admin.register(ModerationAction)
class ModerationActionAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("id", "action_type", "moderator", "report", "actor_target", "post_target", "applied_at")
	list_filter = ("action_type", "moderator")
	search_fields = ("notes", "report__id", "actor_target__handle", "post_target__id")
	ordering = ("-applied_at",)
	readonly_fields = ("id", "report", "actor_target", "post_target", "moderator", "action_type", "notes", "applied_at")


@admin.register(ModerationNote)
class ModerationNoteAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("id", "report", "author", "created_at")
	list_filter = ("author",)
	search_fields = ("body", "report__id", "author__username")
	ordering = ("-created_at",)
	readonly_fields = ("id", "report", "author", "body", "created_at", "updated_at")


@admin.register(SecurityAuditEvent)
class SecurityAuditEventAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("id", "user", "event_type", "ip_address", "created_at")
	list_filter = ("event_type", "created_at")
	search_fields = ("user__email", "event_type", "ip_address", "user_agent")
	ordering = ("-created_at",)
	readonly_fields = ("id", "user", "event_type", "ip_address", "user_agent", "details", "created_at", "updated_at")


@admin.register(TrustSignal)
class TrustSignalAdmin(admin.ModelAdmin):
	list_display = ("actor", "trust_score", "is_throttled", "throttle_reason", "last_computed_at")
	list_filter = ("is_throttled",)
	search_fields = ("actor__handle", "throttle_reason")
	readonly_fields = (
		"id",
		"actor",
		"account_age_days",
		"email_verified",
		"email_verified_at",
		"recent_reports_count",
		"recent_actions_count",
		"posts_last_hour",
		"follows_last_hour",
		"likes_last_hour",
		"reposts_last_hour",
		"trust_score",
		"last_computed_at",
		"created_at",
		"updated_at",
	)
	fields = (
		"id",
		"actor",
		"account_age_days",
		"email_verified",
		"email_verified_at",
		"recent_reports_count",
		"recent_actions_count",
		"posts_last_hour",
		"follows_last_hour",
		"likes_last_hour",
		"reposts_last_hour",
		"trust_score",
		"is_throttled",
		"throttle_reason",
		"throttled_until",
		"last_computed_at",
		"created_at",
		"updated_at",
	)
