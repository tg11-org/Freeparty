from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, User


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
