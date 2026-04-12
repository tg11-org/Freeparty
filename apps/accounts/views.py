from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms import SignUpForm
from apps.accounts.services import VerificationService
from apps.accounts.tasks import send_verification_email


@method_decorator(ratelimit(key="ip", rate="10/m", block=True), name="dispatch")
class RateLimitedLoginView(LoginView):
	template_name = "accounts/login.html"


class RateLimitedLogoutView(LogoutView):
	pass


@method_decorator(ratelimit(key="ip", rate="5/m", block=True), name="dispatch")
class RateLimitedPasswordResetView(PasswordResetView):
	template_name = "accounts/password_reset_form.html"
	email_template_name = "accounts/password_reset_email.txt"


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
		messages.success(request, "Email verified successfully.")
	return redirect("home")


@ratelimit(key="user_or_ip", rate="3/h", block=True)
@require_http_methods(["POST"])
def resend_verification_view(request: HttpRequest) -> HttpResponse:
	if not request.user.is_authenticated:
		return redirect("accounts:login")
	if settings.EMAIL_VERIFICATION_REQUIRED and not request.user.email_verified:
		send_verification_email.delay(str(request.user.id))
		messages.success(request, "Verification email resent.")
	return redirect("home")
