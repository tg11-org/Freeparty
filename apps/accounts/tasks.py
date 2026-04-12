from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse

from apps.accounts.services import VerificationService

User = get_user_model()


@shared_task
def send_verification_email(user_id: str) -> None:
    user = User.objects.get(id=user_id)
    token = VerificationService.create_token(user)
    verify_path = reverse("accounts:verify-email", kwargs={"token": token})
    verify_url = f"{settings.SITE_URL}{verify_path}"
    send_mail(
        subject="Verify your Freeparty email",
        message=f"Verify your email by visiting: {verify_url}",
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


@shared_task
def send_password_reset_notice(email: str) -> None:
    send_mail(
        subject="Freeparty password reset requested",
        message="A password reset was requested for your account.",
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )
