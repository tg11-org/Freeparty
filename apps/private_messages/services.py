from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

import hashlib
import secrets
import uuid

from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageEnvelope, UserIdentityKey


def is_private_messages_enabled() -> bool:
    return bool(getattr(settings, "FEATURE_PM_E2E_ENABLED", False))


def require_private_messages_enabled() -> None:
    if not is_private_messages_enabled():
        raise ImproperlyConfigured("Private messaging is disabled by FEATURE_PM_E2E_ENABLED.")


def create_direct_conversation(*, created_by, participant_a, participant_b) -> Conversation:
    require_private_messages_enabled()
    if participant_a == participant_b:
        raise ValidationError("Direct conversation requires two distinct participants.")

    with transaction.atomic():
        conversation = Conversation.objects.create(
            created_by=created_by,
            conversation_type=Conversation.ConversationType.DIRECT,
        )
        ConversationParticipant.objects.create(conversation=conversation, actor=participant_a)
        ConversationParticipant.objects.create(conversation=conversation, actor=participant_b)
    return conversation


def get_or_create_direct_conversation(*, created_by, participant_a, participant_b) -> tuple[Conversation, bool]:
    require_private_messages_enabled()
    if participant_a == participant_b:
        raise ValidationError("Direct conversation requires two distinct participants.")

    existing = (
        Conversation.objects.filter(conversation_type=Conversation.ConversationType.DIRECT)
        .annotate(
            participant_count=Count("participants", distinct=True),
            matched_participant_count=Count(
                "participants__actor",
                filter=Q(participants__actor__in=[participant_a, participant_b]),
                distinct=True,
            ),
        )
        .filter(participant_count=2, matched_participant_count=2)
        .distinct()
        .first()
    )
    if existing is not None:
        return existing, False

    return create_direct_conversation(
        created_by=created_by,
        participant_a=participant_a,
        participant_b=participant_b,
    ), True


def store_encrypted_message(
    *,
    conversation,
    sender,
    ciphertext: str,
    message_nonce: str,
    sender_key_id: str,
    recipient_key_id: str,
    recipient_actor=None,
    key_epoch: int = 1,
    aad_hash: str = "",
    encryption_scheme: str = EncryptedMessageEnvelope.EncryptionScheme.XCHACHA20POLY1305,
    client_message_id: str = "",
) -> EncryptedMessageEnvelope:
    require_private_messages_enabled()

    required_fields = {
        "ciphertext": ciphertext,
        "message_nonce": message_nonce,
        "sender_key_id": sender_key_id,
        "recipient_key_id": recipient_key_id,
    }
    missing = [field for field, value in required_fields.items() if not value]
    if missing:
        raise ValidationError(f"Encrypted message is missing required fields: {', '.join(missing)}")

    return EncryptedMessageEnvelope.objects.create(
        conversation=conversation,
        sender=sender,
        recipient_actor=recipient_actor,
        ciphertext=ciphertext,
        message_nonce=message_nonce,
        sender_key_id=sender_key_id,
        recipient_key_id=recipient_key_id,
        key_epoch=key_epoch,
        aad_hash=aad_hash,
        encryption_scheme=encryption_scheme,
        client_message_id=client_message_id,
    )


def send_direct_encrypted_message(*, conversation, sender, ciphertext: str, message_nonce: str, client_message_id: str = "") -> EncryptedMessageEnvelope:
    require_private_messages_enabled()

    participants = list(conversation.participants.select_related("actor").all())
    sender_participant = next((participant for participant in participants if participant.actor_id == sender.id), None)
    if sender_participant is None:
        raise ValidationError("Sender is not a participant in this conversation.")
    if conversation.conversation_type != Conversation.ConversationType.DIRECT:
        raise ValidationError("Encrypted send flow currently supports direct conversations only.")

    recipient_participant = next((participant for participant in participants if participant.actor_id != sender.id), None)
    if recipient_participant is None:
        raise ValidationError("Direct conversation recipient could not be resolved.")

    sender_key = UserIdentityKey.objects.filter(actor=sender, is_active=True).order_by("-created_at").first()
    recipient_key = UserIdentityKey.objects.filter(actor=recipient_participant.actor, is_active=True).order_by("-created_at").first()
    if sender_key is None or recipient_key is None:
        raise ValidationError("Both participants need active identity keys before sending encrypted messages.")

    return store_encrypted_message(
        conversation=conversation,
        sender=sender,
        recipient_actor=recipient_participant.actor,
        ciphertext=ciphertext,
        message_nonce=message_nonce,
        sender_key_id=sender_key.key_id,
        recipient_key_id=recipient_key.key_id,
        client_message_id=client_message_id,
    )


def ensure_active_identity_key(*, actor, rotate: bool = False) -> tuple[UserIdentityKey, bool]:
    """Create a local active identity key when missing, or rotate when requested.

    This is a Phase 5 bootstrap utility for local PM testing and onboarding.
    """

    require_private_messages_enabled()
    existing_active = UserIdentityKey.objects.filter(actor=actor, is_active=True).order_by("-created_at").first()
    if existing_active is not None and not rotate:
        return existing_active, False

    if rotate:
        UserIdentityKey.objects.filter(actor=actor, is_active=True).update(is_active=False, rotated_at=timezone.now(), updated_at=timezone.now())

    public_key = f"local-bootstrap:{secrets.token_urlsafe(32)}"
    fingerprint_hex = hashlib.sha256(public_key.encode("utf-8")).hexdigest()
    new_key = UserIdentityKey.objects.create(
        actor=actor,
        key_id=f"{actor.handle}-{uuid.uuid4().hex[:12]}",
        public_key=public_key,
        fingerprint_hex=fingerprint_hex,
        algorithm=UserIdentityKey.Algorithm.ED25519,
        is_active=True,
    )
    return new_key, True


def register_browser_identity_key(*, actor, key_id: str, public_key: str, fingerprint_hex: str) -> tuple[UserIdentityKey, bool]:
    """Register a browser-generated public identity key and rotate previous active keys.

    The browser retains the private key locally; server stores only public key metadata.
    """

    require_private_messages_enabled()
    key_id = (key_id or "").strip()
    public_key = (public_key or "").strip()
    fingerprint_hex = (fingerprint_hex or "").strip().lower()
    if not key_id or not public_key or len(fingerprint_hex) != 64:
        raise ValidationError("key_id, public_key, and 64-char fingerprint_hex are required.")

    with transaction.atomic():
        existing = UserIdentityKey.objects.filter(key_id=key_id).select_related("actor").select_for_update().first()
        if existing is not None and existing.actor.pk != actor.pk:
            raise ValidationError("Identity key id is already registered to another actor.")

        if existing is not None:
            if not existing.is_active:
                UserIdentityKey.objects.filter(actor=actor, is_active=True).exclude(pk=existing.pk).update(
                    is_active=False,
                    rotated_at=timezone.now(),
                    updated_at=timezone.now(),
                )
                existing.is_active = True
                existing.rotated_at = None
                existing.save(update_fields=["is_active", "rotated_at", "updated_at"])
            return existing, False

        UserIdentityKey.objects.filter(actor=actor, is_active=True).update(
            is_active=False,
            rotated_at=timezone.now(),
            updated_at=timezone.now(),
        )
        created = UserIdentityKey.objects.create(
            actor=actor,
            key_id=key_id,
            public_key=public_key,
            fingerprint_hex=fingerprint_hex,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
            is_active=True,
        )
    return created, True
