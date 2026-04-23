from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
import logging

from apps.accounts.forms import (
	AccountDeactivationForm,
	AccountDeletionRequestForm,
	AsyncPasswordResetForm,
	SignUpForm,
)
from apps.accounts.models import AccountActionToken
from apps.accounts.services import AccountLifecycleService, VerificationService
from apps.accounts.tasks import send_verification_email
from apps.profiles.views import initialize_minor_profile_for_signup
from apps.moderation.services import SecurityAuditService


logger = logging.getLogger(__name__)
_TOTP_PENDING_SESSION_KEY = "totp_pending_user_id"
_TOTP_RECOVERY_CODES_SESSION_KEY = "totp_recovery_codes"


@method_decorator(ratelimit(key="ip", rate="10/m", block=True), name="dispatch")
class RateLimitedLoginView(LoginView):
	template_name = "accounts/login.html"

	def form_valid(self, form):
		"""Log successful login; redirect to TOTP step if the user has MFA enabled."""
		from apps.accounts.models import TOTPDevice

		user = form.get_user()

		# Check for a verified TOTP device before completing login.
		try:
			device = user.totp_device
			if device.verified:
				# Don't call super() — that would log the user in immediately.
				# Instead stash the user id and redirect to the TOTP confirm step.
				self.request.session[_TOTP_PENDING_SESSION_KEY] = str(user.id)
				ip_address = self._get_client_ip(self.request)
				user_agent = self.request.headers.get("User-Agent", "")
				SecurityAuditService.log_login_success(
					user,
					ip_address=ip_address,
					user_agent=user_agent,
				)
				return redirect("accounts:totp-confirm")
		except TOTPDevice.DoesNotExist:
			pass

		response = super().form_valid(form)

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
			except User.DoesNotExist:
				pass
			except Exception as exc:
				logger.warning("Failed to record login failure audit event: %s", exc)
		
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
	next_page = reverse_lazy("accounts:logged-out")


@require_http_methods(["GET"])
def logged_out_view(request: HttpRequest) -> HttpResponse:
	return render(request, "accounts/logged_out.html")


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
		except User.DoesNotExist:
			pass
		except Exception as exc:
			logger.warning("Failed to record password reset request audit event: %s", exc)
		
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
		if form.cleaned_data.get("is_under_18"):
			initialize_minor_profile_for_signup(
				request,
				user.actor.profile,
				form.cleaned_data.get("guardian_email", ""),
			)
		login(request, user)
		send_verification_email.delay(str(user.id))
		if form.cleaned_data.get("is_under_18"):
			messages.success(request, "Account created. Check your email to verify your address, and ask your parent or guardian to check their email to finish minor account setup.")
		else:
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

	from apps.accounts.models import TOTPDevice

	try:
		totp_device = request.user.totp_device
	except TOTPDevice.DoesNotExist:
		totp_device = None

	return render(
		request,
		"accounts/account_lifecycle.html",
		{
			"deactivate_form": deactivate_form,
			"delete_form": delete_form,
			"deactivation_retention_days": int(getattr(settings, "ACCOUNT_DEACTIVATION_RETENTION_DAYS", 365)),
			"deletion_retention_days": int(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30)),
			"totp_device": totp_device,
			"recovery_code_count": request.user.recovery_codes.filter(used_at__isnull=True).count() if totp_device and totp_device.verified else 0,
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


# ---------------------------------------------------------------------------
# TOTP / MFA views
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def enroll_totp_view(request: HttpRequest) -> HttpResponse:
	"""Allow an authenticated user to enrol a TOTP device."""
	import io
	import base64
	import pyotp
	import qrcode
	from apps.accounts.models import RecoveryCode, TOTPDevice

	# If already enrolled and verified, redirect to settings.
	try:
		device = request.user.totp_device
		if device.verified:
			messages.info(request, "Two-factor authentication is already enabled.")
			return redirect("accounts:manage")
	except TOTPDevice.DoesNotExist:
		device = None

	if request.method == "POST":
		code = (request.POST.get("code") or "").strip()
		secret = request.POST.get("secret", "")
		if not secret:
			messages.error(request, "Session expired. Please try again.")
			return redirect("accounts:totp-enroll")
		totp = pyotp.TOTP(secret)
		if totp.verify(code, valid_window=1):
			TOTPDevice.objects.update_or_create(
				user=request.user,
				defaults={"secret": secret, "verified": True},
			)
			recovery_codes = RecoveryCode.replace_codes_for_user(user=request.user)
			request.session[_TOTP_RECOVERY_CODES_SESSION_KEY] = recovery_codes
			messages.success(request, "Two-factor authentication enabled successfully. Save your recovery codes now.")
			return redirect("accounts:recovery-codes")
		else:
			messages.error(request, "Invalid code. Please try again.")
			# Fall through to re-render with same secret.

	# GET: generate a new secret each time we render.
	secret = pyotp.random_base32()
	issuer = "Freeparty"
	totp_uri = pyotp.TOTP(secret).provisioning_uri(name=request.user.email, issuer_name=issuer)

	# Build QR code as base-64 data URI.
	img = qrcode.make(totp_uri)
	buffer = io.BytesIO()
	img.save(buffer, format="PNG")
	qr_b64 = base64.b64encode(buffer.getvalue()).decode()

	return render(
		request,
		"accounts/totp_enroll.html",
		{"secret": secret, "qr_b64": qr_b64},
	)


@require_http_methods(["GET", "POST"])
def totp_confirm_login_view(request: HttpRequest) -> HttpResponse:
	"""Second step of login: verify TOTP code for users with an enrolled device."""
	import pyotp
	from apps.accounts.models import RecoveryCode, TOTPDevice

	pending_id = request.session.get(_TOTP_PENDING_SESSION_KEY)
	if not pending_id:
		return redirect("accounts:login")

	if request.method == "POST":
		code = (request.POST.get("code") or "").strip()
		try:
			device = TOTPDevice.objects.select_related("user").get(user_id=pending_id, verified=True)
		except TOTPDevice.DoesNotExist:
			messages.error(request, "Authentication device not found.")
			return redirect("accounts:login")

		totp = pyotp.TOTP(device.secret)
		if totp.verify(code, valid_window=1):
			del request.session[_TOTP_PENDING_SESSION_KEY]
			login(request, device.user, backend="django.contrib.auth.backends.ModelBackend")
			return redirect(settings.LOGIN_REDIRECT_URL)

		for recovery_code in RecoveryCode.objects.filter(user_id=pending_id, used_at__isnull=True).order_by("created_at"):
			if recovery_code.matches(code):
				recovery_code.mark_used()
				del request.session[_TOTP_PENDING_SESSION_KEY]
				login(request, device.user, backend="django.contrib.auth.backends.ModelBackend")
				messages.warning(request, "Signed in with a recovery code. That code has now been consumed.")
				return redirect(settings.LOGIN_REDIRECT_URL)

		messages.error(request, "Invalid authenticator or recovery code. Please try again.")

	return render(
		request,
		"accounts/totp_confirm.html",
		{"recovery_code_count": RecoveryCode.objects.filter(user_id=pending_id, used_at__isnull=True).count()},
	)


@login_required
@require_http_methods(["GET"])
def recovery_codes_view(request: HttpRequest) -> HttpResponse:
	from apps.accounts.models import TOTPDevice

	try:
		device = request.user.totp_device
	except TOTPDevice.DoesNotExist:
		messages.error(request, "Enable two-factor authentication before managing recovery codes.")
		return redirect("accounts:manage")

	if not device.verified:
		messages.error(request, "Finish enabling two-factor authentication first.")
		return redirect("accounts:totp-enroll")

	recovery_codes = request.session.pop(_TOTP_RECOVERY_CODES_SESSION_KEY, None)
	return render(
		request,
		"accounts/recovery_codes.html",
		{
			"recovery_codes": recovery_codes,
			"remaining_recovery_code_count": request.user.recovery_codes.filter(used_at__isnull=True).count(),
		},
	)


@login_required
@require_http_methods(["POST"])
def regenerate_recovery_codes_view(request: HttpRequest) -> HttpResponse:
	from apps.accounts.models import RecoveryCode, TOTPDevice

	try:
		device = request.user.totp_device
	except TOTPDevice.DoesNotExist:
		messages.error(request, "Enable two-factor authentication before generating recovery codes.")
		return redirect("accounts:manage")

	if not device.verified:
		messages.error(request, "Finish enabling two-factor authentication first.")
		return redirect("accounts:totp-enroll")

	recovery_codes = RecoveryCode.replace_codes_for_user(user=request.user)
	request.session[_TOTP_RECOVERY_CODES_SESSION_KEY] = recovery_codes
	messages.success(request, "Recovery codes regenerated. Save the new set now; the old codes no longer work.")
	return redirect("accounts:recovery-codes")


@login_required
@require_http_methods(["POST"])
def disable_totp_view(request: HttpRequest) -> HttpResponse:
	"""Remove the user's TOTP device."""
	from apps.accounts.models import RecoveryCode, TOTPDevice

	try:
		device = request.user.totp_device
	except TOTPDevice.DoesNotExist:
		messages.error(request, "No two-factor device found.")
		return redirect("accounts:manage")

	RecoveryCode.objects.filter(user=request.user).delete()
	device.delete()
	request.session.pop(_TOTP_RECOVERY_CODES_SESSION_KEY, None)
	messages.success(request, "Two-factor authentication disabled.")
	return redirect("accounts:manage")
