from django.contrib import admin

from apps.federation.models import FederationDelivery, FederationObject, Instance


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
	list_display = ("domain", "software_name", "software_version", "is_blocked", "last_seen_at")
	list_filter = ("is_blocked",)
	search_fields = ("domain",)


admin.site.register(FederationObject)
admin.site.register(FederationDelivery)
