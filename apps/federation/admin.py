from django.contrib import admin

from apps.federation.models import FederationDelivery, FederationObject, Instance, RemoteActor, RemotePost


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
	list_display = ("domain", "allowlist_state", "is_blocked", "added_by", "software_name", "software_version", "last_seen_at")
	list_filter = ("allowlist_state", "is_blocked")
	search_fields = ("domain",)
	readonly_fields = ("last_seen_at", "created_at", "updated_at")
	actions = ("mark_allowlisted", "mark_pending", "mark_blocked")

	@admin.action(description="Mark selected instances as allowlisted")
	def mark_allowlisted(self, request, queryset):
		updated = queryset.update(allowlist_state=Instance.AllowlistState.ALLOWED, is_blocked=False)
		self.message_user(request, f"Allowlisted {updated} instance(s).")

	@admin.action(description="Mark selected instances as pending")
	def mark_pending(self, request, queryset):
		updated = queryset.update(allowlist_state=Instance.AllowlistState.PENDING, is_blocked=False)
		self.message_user(request, f"Set {updated} instance(s) to pending.")

	@admin.action(description="Mark selected instances as blocked")
	def mark_blocked(self, request, queryset):
		updated = queryset.update(allowlist_state=Instance.AllowlistState.BLOCKED, is_blocked=True)
		self.message_user(request, f"Blocked {updated} instance(s).")


@admin.register(FederationObject)
class FederationObjectAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("id", "object_type", "instance", "processing_state", "fetched_at", "created_at")
	list_filter = ("object_type", "processing_state", "created_at")
	search_fields = ("id", "canonical_uri", "external_id", "instance__domain")
	readonly_fields = (
		"id",
		"instance",
		"canonical_uri",
		"external_id",
		"object_type",
		"payload",
		"signature_metadata",
		"fetched_at",
		"processing_state",
		"created_at",
		"updated_at",
	)


@admin.register(FederationDelivery)
class FederationDeliveryAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("id", "target_instance", "state", "retry_count", "response_code", "last_attempted_at")
	list_filter = ("state",)
	search_fields = ("id", "target_instance__domain", "object_uri", "response_body")
	readonly_fields = (
		"id",
		"target_instance",
		"actor",
		"object_uri",
		"activity_payload",
		"state",
		"retry_count",
		"last_attempted_at",
		"response_code",
		"response_body",
		"created_at",
		"updated_at",
	)


@admin.register(RemoteActor)
class RemoteActorAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("handle", "instance", "canonical_uri", "fetched_at")
	search_fields = ("handle", "display_name", "canonical_uri", "instance__domain")
	readonly_fields = ("id", "instance", "handle", "display_name", "canonical_uri", "public_key", "avatar_url", "fetched_at", "created_at", "updated_at")


@admin.register(RemotePost)
class RemotePostAdmin(ImmutableAdminMixin, admin.ModelAdmin):
	list_display = ("canonical_uri", "instance", "remote_actor", "fetched_at")
	search_fields = ("canonical_uri", "remote_actor__handle", "instance__domain")
	readonly_fields = ("id", "instance", "remote_actor", "canonical_uri", "content", "attachments", "metadata", "fetched_at", "created_at", "updated_at")
