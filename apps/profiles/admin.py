from django.contrib import admin

from apps.profiles.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = ("actor", "website_url", "location", "updated_at")
	search_fields = ("actor__handle", "location")
