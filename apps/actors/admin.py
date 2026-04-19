from django.contrib import admin

from apps.actors.models import Actor


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
	list_display = (
		"handle",
		"is_verified",
		"handle_locked",
		"actor_type",
		"state",
		"remote_domain",
		"created_at",
	)
	list_filter = ("actor_type", "state", "is_verified", "handle_locked")
	search_fields = ("handle", "canonical_uri", "remote_domain", "user__email")
