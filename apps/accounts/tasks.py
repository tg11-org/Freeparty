from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse

from apps.accounts.services import VerificationService
from apps.core.services.task_observability import observe_celery_task

User = get_user_model()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_verification_email(self, user_id: str, correlation_id: str | None = None) -> None:
    with observe_celery_task(self, correlation_id=correlation_id):
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


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_password_reset_notice(self, email: str, correlation_id: str | None = None) -> None:
    with observe_celery_task(self, correlation_id=correlation_id):
        send_mail(
            subject="Freeparty password reset requested",
            message="A password reset was requested for your account.",
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )
