from django.contrib import admin

from apps.profiles.models import (
	GuardianEmailVerificationToken,
	ParentalControlChangeRequest,
	Profile,
	ProfileEditHistory,
	ProfileLink,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = (
		"actor",
		"website_url",
		"location",
		"is_minor_account",
		"parental_controls_enabled",
		"auto_reveal_spoilers",
		"updated_at",
	)
	search_fields = ("actor__handle", "location")


@admin.register(ProfileEditHistory)
class ProfileEditHistoryAdmin(admin.ModelAdmin):
	list_display = ("profile", "editor", "created_at")
	search_fields = ("profile__actor__handle", "editor__username", "editor__email")


@admin.register(ProfileLink)
class ProfileLinkAdmin(admin.ModelAdmin):
	list_display = ("profile", "title", "display_order", "is_active", "updated_at")
	search_fields = ("profile__actor__handle", "title", "url")
	list_filter = ("is_active",)


@admin.register(GuardianEmailVerificationToken)
class GuardianEmailVerificationTokenAdmin(admin.ModelAdmin):
	list_display = ("profile", "guardian_email", "expires_at", "used_at", "created_at")
	search_fields = ("profile__actor__handle", "guardian_email", "token")


@admin.register(ParentalControlChangeRequest)
class ParentalControlChangeRequestAdmin(admin.ModelAdmin):
	list_display = ("profile", "guardian_email", "requested_by", "expires_at", "used_at", "created_at")
	search_fields = ("profile__actor__handle", "guardian_email", "token")
