from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from apps.accounts.services import AccountLifecycleService
from apps.accounts.tasks import send_verification_email
from apps.accounts.models import AccountActionToken, EmailVerificationToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	actions = ["resend_verification_emails", "send_reactivation_links", "send_deletion_cancellation_links"]
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

	@admin.action(permissions=["resend_verification"], description="Resend verification email for selected users")
	def resend_verification_emails(self, request, queryset):
		eligible = queryset.filter(email_verified_at__isnull=True)
		count = 0
		for user in eligible:
			send_verification_email.delay(str(user.id))
			count += 1
		self.message_user(request, f"Queued verification emails for {count} user(s).")

	@admin.action(permissions=["account_lifecycle_support"], description="Send reactivation links to selected deactivated users")
	def send_reactivation_links(self, request, queryset):
		count = 0
		for user in queryset.filter(is_active=False, deactivated_at__isnull=False):
			retention_days = int(getattr(settings, "ACCOUNT_DEACTIVATION_RETENTION_DAYS", 365))
			token = AccountLifecycleService.create_action_token(
				user=user,
				action=AccountActionToken.ActionType.REACTIVATE,
				ttl_hours=max(24, retention_days * 24),
			)
			reactivate_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{reverse('accounts:reactivate-account', kwargs={'token': token})}"
			send_mail(
				subject="Freeparty account reactivation link",
				message=(
					"A support reactivation link was requested for your account. Use this link if you want to restore access:\n\n"
					f"{reactivate_url}"
				),
				from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
				recipient_list=[user.email],
				fail_silently=True,
			)
			count += 1
		self.message_user(request, f"Sent reactivation links for {count} user(s).")

	@admin.action(permissions=["account_lifecycle_support"], description="Send deletion-cancellation links to selected users")
	def send_deletion_cancellation_links(self, request, queryset):
		count = 0
		for user in queryset.filter(deletion_scheduled_for_at__isnull=False):
			retention_days = int(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30))
			token = AccountLifecycleService.create_action_token(
				user=user,
				action=AccountActionToken.ActionType.CANCEL_DELETION,
				ttl_hours=max(24, retention_days * 24),
			)
			cancel_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{reverse('accounts:cancel-account-deletion', kwargs={'token': token})}"
			send_mail(
				subject="Freeparty account deletion cancellation link",
				message=(
					"A support cancellation link was requested for your scheduled account deletion. Use this link to keep the account active:\n\n"
					f"{cancel_url}"
				),
				from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
				recipient_list=[user.email],
				fail_silently=True,
			)
			count += 1
		self.message_user(request, f"Sent deletion cancellation links for {count} user(s).")

	def has_resend_verification_permission(self, request):
		return request.user.is_superuser or request.user.has_perm("accounts.resend_verification_email")

	def has_account_lifecycle_support_permission(self, request):
		return request.user.is_superuser or request.user.has_perm("accounts.manage_account_lifecycle_support")


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
