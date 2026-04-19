from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import (
	AccountDeactivationForm,
	AccountDeletionRequestForm,
	AsyncPasswordResetForm,
	SignUpForm,
)
from apps.accounts.models import AccountActionToken
from apps.accounts.services import AccountLifecycleService, VerificationService
from apps.accounts.tasks import send_verification_email
from apps.moderation.services import SecurityAuditService


@method_decorator(ratelimit(key="ip", rate="10/m", block=True), name="dispatch")
class RateLimitedLoginView(LoginView):
	template_name = "accounts/login.html"

	def form_valid(self, form):
		"""Log successful login and record audit event."""
		response = super().form_valid(form)
		user = form.get_user()
		
		# Log security audit event
		ip_address = self._get_client_ip(self.request)
		user_agent = self.request.headers.get("User-Agent", "")
		SecurityAuditService.log_login_success(
			user,
			ip_address=ip_address,
			user_agent=user_agent,
		)
		
		return response

	def form_invalid(self, form):
		"""Log failed login attempts."""
		email = form.cleaned_data.get("username")  # django login view uses 'username' field
		if email:
			try:
				from apps.accounts.models import User
				user = User.objects.get(email=email)
				ip_address = self._get_client_ip(self.request)
				user_agent = self.request.headers.get("User-Agent", "")
				SecurityAuditService.log_login_failure(
					user,
					ip_address=ip_address,
					user_agent=user_agent,
					reason="invalid_password",
				)
			except Exception:
				pass  # User doesn't exist or other issue, don't expose in logs
		
		return super().form_invalid(form)

	def _get_client_ip(self, request):
		"""Extract client IP address from request, accounting for proxies."""
		x_forwarded_for = request.headers.get("X-Forwarded-For", "")
		if x_forwarded_for:
			ip = x_forwarded_for.split(",")[0].strip()
		else:
			ip = request.META.get("REMOTE_ADDR", "")
		return ip


class RateLimitedLogoutView(LogoutView):
	next_page = "home"


@method_decorator(ratelimit(key="ip", rate="5/m", block=True), name="dispatch")
class RateLimitedPasswordResetView(PasswordResetView):
	template_name = "accounts/password_reset_form.html"
	email_template_name = "accounts/password_reset_email.txt"
	form_class = AsyncPasswordResetForm
	success_url = reverse_lazy("accounts:password-reset-done")

	def form_valid(self, form):
		"""Log password reset request."""
		response = super().form_valid(form)
		try:
			from apps.accounts.models import User
			user = User.objects.get(email=form.cleaned_data["email"])
			ip_address = self._get_client_ip(self.request)
			user_agent = self.request.headers.get("User-Agent", "")
			SecurityAuditService.log_password_reset_request(
				user,
				ip_address=ip_address,
				user_agent=user_agent,
			)
		except Exception:
			pass  # User not found or other issue
		
		return response

	def _get_client_ip(self, request):
		"""Extract client IP address from request, accounting for proxies."""
		x_forwarded_for = request.headers.get("X-Forwarded-For", "")
		if x_forwarded_for:
			ip = x_forwarded_for.split(",")[0].strip()
		else:
			ip = request.META.get("REMOTE_ADDR", "")
		return ip


class RateLimitedPasswordResetConfirmView(PasswordResetConfirmView):
	"""Custom password reset confirm to log completion."""

	def form_valid(self, form):
		"""Log password reset completion."""
		response = super().form_valid(form)
		user = form.save()
		
		ip_address = self._get_client_ip(self.request)
		user_agent = self.request.headers.get("User-Agent", "")
		SecurityAuditService.log_password_reset_complete(
			user,
			ip_address=ip_address,
			user_agent=user_agent,
		)
		
		return response

	def _get_client_ip(self, request):
		"""Extract client IP address from request, accounting for proxies."""
		x_forwarded_for = request.headers.get("X-Forwarded-For", "")
		if x_forwarded_for:
			ip = x_forwarded_for.split(",")[0].strip()
		else:
			ip = request.META.get("REMOTE_ADDR", "")
		return ip


@ratelimit(key="ip", rate="5/m", block=True)
@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
	form = SignUpForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		user = form.save()
		login(request, user)
		send_verification_email.delay(str(user.id))
		messages.success(request, "Account created. Check your email to verify your address.")
		return redirect("home")
	return render(request, "accounts/signup.html", {"form": form})


@require_http_methods(["GET"])
def verify_email_view(request: HttpRequest, token: str) -> HttpResponse:
	user = VerificationService.verify_token(token)
	if not user:
		messages.error(request, "Verification link is invalid or expired.")
	else:
		# Log email verification event
		ip_address = _get_client_ip(request)
		user_agent = request.headers.get("User-Agent", "")
		SecurityAuditService.log_email_verification(
			user,
			ip_address=ip_address,
			user_agent=user_agent,
		)
		messages.success(request, "Email verified successfully.")
	return redirect("home")


def _get_client_ip(request):
	"""Extract client IP address from request, accounting for proxies."""
	x_forwarded_for = request.headers.get("X-Forwarded-For", "")
	if x_forwarded_for:
		ip = x_forwarded_for.split(",")[0].strip()
	else:
		ip = request.META.get("REMOTE_ADDR", "")
	return ip


@ratelimit(key="user_or_ip", rate="3/h", block=True)
@require_http_methods(["POST"])
def resend_verification_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect("accounts:login")
	if settings.EMAIL_VERIFICATION_REQUIRED and not request.user.email_verified:
		send_verification_email.delay(str(request.user.id))
		messages.success(request, "Verification email resent.")
	return redirect("home")


@require_http_methods(["GET", "POST"])
def account_lifecycle_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect("accounts:login")

	deactivate_form = AccountDeactivationForm()
	delete_form = AccountDeletionRequestForm()

	if request.method == "POST":
		action = request.POST.get("action", "")
		if action == "deactivate":
			deactivate_form = AccountDeactivationForm(request.POST)
			if deactivate_form.is_valid():
				retention_days = int(getattr(settings, "ACCOUNT_DEACTIVATION_RETENTION_DAYS", 365))
				request.user.deactivate_account(retention_days=retention_days)
				token = AccountLifecycleService.create_action_token(
					user=request.user,
					action=AccountActionToken.ActionType.REACTIVATE,
					ttl_hours=max(24, retention_days * 24),
				)
				recovery_url = request.build_absolute_uri(reverse("accounts:reactivate-account", kwargs={"token": token}))
				send_mail(
					subject="Freeparty account reactivation link",
					message=(
						"Your account was deactivated. If this was not you or you changed your mind, reactivate with this link:\n\n"
						f"{recovery_url}\n\n"
						"This link expires according to your account retention window."
					),
					from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
					recipient_list=[request.user.email],
					fail_silently=True,
				)
				logout(request)
				messages.success(request, "Account deactivated. A reactivation link was sent to your email.")
				return redirect("home")
		elif action == "delete":
			delete_form = AccountDeletionRequestForm(request.POST)
			if delete_form.is_valid():
				retention_days = int(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30))
				request.user.request_account_deletion(retention_days=retention_days)
				token = AccountLifecycleService.create_action_token(
					user=request.user,
					action=AccountActionToken.ActionType.CANCEL_DELETION,
					ttl_hours=max(24, retention_days * 24),
				)
				cancel_url = request.build_absolute_uri(reverse("accounts:cancel-account-deletion", kwargs={"token": token}))
				send_mail(
					subject="Freeparty account deletion scheduled",
					message=(
						"Your account deletion request was scheduled. If this was not you or you changed your mind, cancel with this link:\n\n"
						f"{cancel_url}\n\n"
						f"Scheduled deletion date: {request.user.deletion_scheduled_for_at:%Y-%m-%d %H:%M UTC}"
					),
					from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
					recipient_list=[request.user.email],
					fail_silently=True,
				)
				logout(request)
				messages.success(request, "Deletion requested. A cancellation link was sent to your email.")
				return redirect("home")

	return render(
		request,
		"accounts/account_lifecycle.html",
		{
			"deactivate_form": deactivate_form,
			"delete_form": delete_form,
			"deactivation_retention_days": int(getattr(settings, "ACCOUNT_DEACTIVATION_RETENTION_DAYS", 365)),
			"deletion_retention_days": int(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30)),
		},
	)


@require_http_methods(["GET"])
def reactivate_account_view(request: HttpRequest, token: str) -> HttpResponse:
	user = AccountLifecycleService.consume_action_token(token=token, expected_action=AccountActionToken.ActionType.REACTIVATE)
	if not user:
		messages.error(request, "Reactivation link is invalid or expired.")
		return redirect("home")
	user.reactivate_account()
	messages.success(request, "Account reactivated. You can log in again.")
	return redirect("accounts:login")


@require_http_methods(["GET"])
def cancel_account_deletion_view(request: HttpRequest, token: str) -> HttpResponse:
	user = AccountLifecycleService.consume_action_token(token=token, expected_action=AccountActionToken.ActionType.CANCEL_DELETION)
	if not user:
		messages.error(request, "Deletion cancellation link is invalid or expired.")
		return redirect("home")
	user.cancel_deletion_request()
	messages.success(request, "Deletion request cancelled. You can log in again.")
	return redirect("accounts:login")
