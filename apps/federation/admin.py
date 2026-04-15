from django.contrib import admin

from apps.federation.models import FederationDelivery, FederationObject, Instance


class ImmutableAdminMixin:
	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
	list_display = ("domain", "software_name", "software_version", "is_blocked", "last_seen_at")
	list_filter = ("is_blocked",)
	search_fields = ("domain",)


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
