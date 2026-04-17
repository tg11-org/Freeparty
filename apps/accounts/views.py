from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import AsyncPasswordResetForm, SignUpForm
from apps.accounts.services import VerificationService
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
