from __future__ import annotations

from datetime import timedelta
import secrets

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccountActionToken, EmailVerificationToken, User


class VerificationService:
    signer = signing.TimestampSigner(salt="accounts.email.verification")

    @classmethod
    def create_token(cls, user: User) -> str:
        payload = f"{user.id}:{user.email}"
        token = cls.signer.sign(payload)
        EmailVerificationToken.objects.create(
            user=user,
            token=token,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        return token

    @classmethod
    def verify_token(cls, token: str) -> User | None:
        max_age = int(getattr(settings, "EMAIL_VERIFICATION_MAX_AGE", 60 * 60 * 24))
        try:
            value = cls.signer.unsign(token, max_age=max_age)
        except signing.BadSignature:
            return None

        try:
            token_obj = EmailVerificationToken.objects.select_related("user").get(token=token)
        except EmailVerificationToken.DoesNotExist:
            return None

        if not token_obj.is_usable:
            return None

        user_id, user_email = value.split(":", 1)
        if str(token_obj.user.id) != user_id or token_obj.user.email != user_email:
            return None

        token_obj.used_at = timezone.now()
        token_obj.save(update_fields=["used_at", "updated_at"])
        token_obj.user.mark_email_verified()
        return token_obj.user


class AccountLifecycleService:
    @staticmethod
    def create_action_token(*, user: User, action: str, ttl_hours: int = 24) -> str:
        token = secrets.token_urlsafe(32)
        AccountActionToken.objects.create(
            user=user,
            action=action,
            token=token,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )
        return token

    @staticmethod
    def consume_action_token(*, token: str, expected_action: str) -> User | None:
        try:
            token_obj = AccountActionToken.objects.select_related("user").get(token=token, action=expected_action)
        except AccountActionToken.DoesNotExist:
            return None

        if not token_obj.is_usable:
            return None

        token_obj.used_at = timezone.now()
        token_obj.save(update_fields=["used_at", "updated_at"])
        return token_obj.user

    @staticmethod
    def purge_expired_accounts(*, dry_run: bool = False) -> dict[str, int]:
        now = timezone.now()

        deletion_qs = User.objects.filter(
            deletion_scheduled_for_at__isnull=False,
            deletion_scheduled_for_at__lte=now,
        )
        deactivation_qs = User.objects.filter(
            deletion_scheduled_for_at__isnull=True,
            deactivation_recovery_deadline_at__isnull=False,
            deactivation_recovery_deadline_at__lte=now,
            is_active=False,
        )

        to_delete_ids = set(deletion_qs.values_list("id", flat=True))
        to_delete_ids.update(deactivation_qs.values_list("id", flat=True))

        result = {
            "purged_total": len(to_delete_ids),
            "purged_after_deletion_window": deletion_qs.count(),
            "purged_after_deactivation_window": deactivation_qs.count(),
        }

        if dry_run or not to_delete_ids:
            return result

        with transaction.atomic():
            User.objects.filter(id__in=to_delete_ids).delete()
        return result
