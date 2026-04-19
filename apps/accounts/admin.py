from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import AccountActionToken, EmailVerificationToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	ordering = ("-created_at",)
	list_display = (
		"email",
		"username",
		"state",
		"is_staff",
		"is_active",
		"email_verified_at",
		"tos_accepted_at",
		"guidelines_accepted_at",
		"created_at",
	)
	list_filter = ("state", "is_staff", "is_active")
	search_fields = ("email", "username", "display_name")
	fieldsets = (
		(None, {"fields": ("email", "username", "password")}),
		("Profile", {"fields": ("display_name", "last_seen_at")}),
		(
			"Verification and Legal",
			{
				"fields": (
					"email_verified_at",
					"state",
					"tos_accepted_at",
					"tos_version_accepted",
					"guidelines_accepted_at",
					"guidelines_version_accepted",
				),
			},
		),
		(
			"Lifecycle",
			{
				"fields": (
					"deactivated_at",
					"deactivation_recovery_deadline_at",
					"deletion_requested_at",
					"deletion_scheduled_for_at",
				),
			},
		),
		("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
		("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
	)
	readonly_fields = ("created_at", "updated_at")
	add_fieldsets = (
		(
			None,
			{
				"classes": ("wide",),
				"fields": ("email", "username", "display_name", "password1", "password2", "is_staff", "is_active"),
			},
		),
	)


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
	list_display = ("user", "token", "expires_at", "used_at", "created_at")
	list_filter = ("used_at",)
	search_fields = ("user__email", "token")


@admin.register(AccountActionToken)
class AccountActionTokenAdmin(admin.ModelAdmin):
	list_display = ("user", "action", "expires_at", "used_at", "created_at")
	list_filter = ("action", "used_at")
	search_fields = ("user__email", "token")
