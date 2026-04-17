from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse

from apps.accounts.services import VerificationService
from apps.core.services.email_observability import log_smtp_delivery_event
from apps.core.services.task_observability import observe_celery_task

User = get_user_model()


def _deliver_transactional_email(
    *,
    task,
    subject: str,
    message: str,
    recipient_list: list[str],
    correlation_id: str | None = None,
    from_email: str | None = None,
    html_message: str | None = None,
) -> None:
    retries = int(getattr(task.request, "retries", 0))
    attempt = retries + 1
    max_retries = int(getattr(task, "max_retries", 0))
    task_id = getattr(task.request, "id", "")
    resolved_from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    recipient_count = len(recipient_list)

    log_smtp_delivery_event(
        event="attempt",
        task_name=task.name,
        task_id=task_id,
        correlation_id=correlation_id,
        recipient_count=recipient_count,
        attempt=attempt,
        max_retries=max_retries,
        will_retry=False,
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=resolved_from_email,
            recipient_list=recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
    except Exception as exc:
        will_retry = retries < max_retries
        log_smtp_delivery_event(
            event="failure",
            task_name=task.name,
            task_id=task_id,
            correlation_id=correlation_id,
            recipient_count=recipient_count,
            attempt=attempt,
            max_retries=max_retries,
            will_retry=will_retry,
            error=exc.__class__.__name__,
        )
        if will_retry:
            log_smtp_delivery_event(
                event="retry_scheduled",
                task_name=task.name,
                task_id=task_id,
                correlation_id=correlation_id,
                recipient_count=recipient_count,
                attempt=attempt + 1,
                max_retries=max_retries,
                will_retry=True,
                error=exc.__class__.__name__,
            )
        raise
    log_smtp_delivery_event(
        event="success",
        task_name=task.name,
        task_id=task_id,
        correlation_id=correlation_id,
        recipient_count=recipient_count,
        attempt=attempt,
        max_retries=max_retries,
        will_retry=False,
    )


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
        _deliver_transactional_email(
            task=self,
            subject="Verify your Freeparty email",
            message=f"Verify your email by visiting: {verify_url}",
            recipient_list=[user.email],
            correlation_id=correlation_id,
        )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_password_reset_email(
    self,
    subject: str,
    message: str,
    recipient_email: str,
    correlation_id: str | None = None,
    from_email: str | None = None,
    html_message: str | None = None,
) -> None:
    with observe_celery_task(self, correlation_id=correlation_id):
        _deliver_transactional_email(
            task=self,
            subject=subject,
            message=message,
            recipient_list=[recipient_email],
            correlation_id=correlation_id,
            from_email=from_email,
            html_message=html_message,
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
        _deliver_transactional_email(
            task=self,
            subject="Freeparty password reset requested",
            message="A password reset was requested for your account.",
            recipient_list=[email],
            correlation_id=correlation_id,
        )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def send_system_email(
    self,
    subject: str,
    message: str,
    recipient_emails: list[str],
    correlation_id: str | None = None,
    from_email: str | None = None,
    html_message: str | None = None,
) -> None:
    with observe_celery_task(self, correlation_id=correlation_id):
        _deliver_transactional_email(
            task=self,
            subject=subject,
            message=message,
            recipient_list=recipient_emails,
            correlation_id=correlation_id,
            from_email=from_email,
            html_message=html_message,
        )
