from datetime import timedelta
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.utils import timezone

import hashlib
import secrets
import uuid

from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageAttachment, EncryptedMessageEnvelope, UserIdentityKey


logger = logging.getLogger("apps.private_messages")


def canonical_direct_participant_key(participant_a, participant_b) -> str:
    participant_ids = sorted([str(participant_a.id), str(participant_b.id)])
    return ":".join(participant_ids)


def _get_profile_or_none(actor):
    try:
        return actor.profile
    except Exception:
        return None


def _is_teen_actor(*, actor) -> bool:
    profile = _get_profile_or_none(actor)
    if profile is None or not profile.is_minor_account:
        return False
    age_years = profile.get_effective_minor_age_years()
    if age_years is None:
        return False
    return 13 <= age_years < 18


def get_parental_dm_restriction_error(*, actor, target_actor) -> str | None:
    actor_profile = _get_profile_or_none(actor)
    target_profile = _get_profile_or_none(target_actor)

    if (
        actor_profile is not None
        and actor_profile.is_minor_account
        and actor_profile.parental_controls_enabled
        and actor_profile.guardian_restrict_dms_to_teens
        and not _is_teen_actor(actor=target_actor)
    ):
        return "Parental controls only allow DMs with teen accounts (13-17)."

    if (
        target_profile is not None
        and target_profile.is_minor_account
        and target_profile.parental_controls_enabled
        and target_profile.guardian_restrict_dms_to_teens
        and not _is_teen_actor(actor=actor)
    ):
        return "This account is protected by parental controls and only accepts DMs from teen accounts (13-17)."

    return None


def is_private_messages_enabled() -> bool:
    return bool(getattr(settings, "FEATURE_PM_E2E_ENABLED", False))


def is_private_message_websocket_enabled() -> bool:
    return is_private_messages_enabled() and bool(getattr(settings, "FEATURE_PM_WEBSOCKET_ENABLED", False))


def is_actor_pm_eligible(*, actor) -> bool:
    """Check if actor is eligible for PM based on rollout policy and feature flag."""
    if not is_private_messages_enabled():
        return False

    from apps.private_messages.models import PMRolloutPolicy

    try:
        policy = PMRolloutPolicy.get_default_instance()
    except Exception:
        # If policy cannot be retrieved, deny access
        return False

    if policy.stage == PMRolloutPolicy.RolloutStage.DISABLED:
        return False
    elif policy.stage == PMRolloutPolicy.RolloutStage.ALLOWLIST:
        return policy.allowlisted_actors.filter(pk=actor.pk).exists()
    elif policy.stage == PMRolloutPolicy.RolloutStage.BETA:
        # BETA mode: all authenticated users can use PM
        return True
    elif policy.stage == PMRolloutPolicy.RolloutStage.GENERAL:
        # GENERAL: all authenticated users can use PM
        return True
    else:
        return False


def serialize_encrypted_envelope(envelope: EncryptedMessageEnvelope) -> dict:
    sender = envelope.sender
    return {
        "id": str(envelope.id),
        "sender_id": str(envelope.sender_id or ""),
        "sender_handle": sender.handle if sender else "unknown",
        "sender_display_name": sender.user.display_name if sender and sender.user and sender.user.display_name else "",
        "ciphertext": envelope.ciphertext,
        "message_nonce": envelope.message_nonce,
        "sender_key_id": envelope.sender_key_id,
        "recipient_key_id": envelope.recipient_key_id,
        "attachments": [
            {
                "id": str(attachment.id),
                "client_attachment_id": attachment.client_attachment_id,
                "encrypted_size": attachment.encrypted_size,
            }
            for attachment in envelope.attachments.all().order_by("created_at", "id")
        ],
        "created_at": envelope.created_at.isoformat(),
    }


def publish_direct_message_event(envelope: EncryptedMessageEnvelope) -> None:
    if not is_private_message_websocket_enabled():
        return
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        payload = {
            "ok": True,
            "type": "dm.envelope",
            "envelope": serialize_encrypted_envelope(envelope),
        }
        async_to_sync(channel_layer.group_send)(
            f"dm_conversation_{envelope.conversation_id}",
            {"type": "dm_envelope", "payload": payload},
        )
    except Exception as exc:
        # WebSocket publishing is best-effort. Do not fail message writes when
        # the channel layer/backplane is temporarily unavailable.
        logger.warning(
            "Failed to publish DM websocket event for envelope %s: %s",
            envelope.id,
            exc,
        )


def get_conversation_queryset_for_actor(*, actor):
    return (
        Conversation.objects.filter(participants__actor=actor)
        .prefetch_related("participants__actor", "participants__actor__profile")
        .distinct()
        .annotate(
            total_message_count=Count("messages", distinct=True),
            latest_message_created_at=Max("messages__created_at"),
        )
        .order_by("-latest_message_created_at", "-updated_at")
    )


def populate_conversation_activity(*, actor, conversations):
    conversations = list(conversations)
    if not conversations:
        return conversations

    participant_rows = ConversationParticipant.objects.filter(
        actor=actor,
        conversation__in=conversations,
    ).values("conversation_id", "joined_at", "last_read_at")
    participant_by_conversation_id = {row["conversation_id"]: row for row in participant_rows}
    unread_counts: dict = {conversation.id: 0 for conversation in conversations}

    incoming_rows = EncryptedMessageEnvelope.objects.filter(
        conversation__in=conversations,
        recipient_actor=actor,
    ).values("conversation_id", "created_at")

    for row in incoming_rows:
        participant = participant_by_conversation_id.get(row["conversation_id"])
        if participant is None:
            continue
        last_read_at = participant["last_read_at"]
        cutoff = last_read_at or participant["joined_at"]
        if cutoff is None:
            unread_counts[row["conversation_id"]] += 1
        elif last_read_at is None and row["created_at"] >= cutoff:
            unread_counts[row["conversation_id"]] += 1
        elif last_read_at is not None and row["created_at"] > cutoff:
            unread_counts[row["conversation_id"]] += 1

    for conversation in conversations:
        conversation.unread_message_count = unread_counts.get(conversation.id, 0)

    return conversations


def get_unread_conversation_count(*, actor) -> int:
    unread_after_last_read = EncryptedMessageEnvelope.objects.filter(
        conversation_id=OuterRef("conversation_id"),
        recipient_actor=actor,
        created_at__gt=OuterRef("last_read_at"),
    )
    unread_since_join = EncryptedMessageEnvelope.objects.filter(
        conversation_id=OuterRef("conversation_id"),
        recipient_actor=actor,
        created_at__gte=OuterRef("joined_at"),
    )
    read_count = (
        ConversationParticipant.objects.filter(actor=actor, last_read_at__isnull=False)
        .annotate(has_unread=Exists(unread_after_last_read))
        .filter(has_unread=True)
        .count()
    )
    never_read_count = (
        ConversationParticipant.objects.filter(actor=actor, last_read_at__isnull=True)
        .annotate(has_unread=Exists(unread_since_join))
        .filter(has_unread=True)
        .count()
    )
    return read_count + never_read_count


def mark_conversation_read(*, conversation, actor, read_through=None):
    participant = ConversationParticipant.objects.filter(conversation=conversation, actor=actor).first()
    if participant is None:
        return None

    incoming_qs = EncryptedMessageEnvelope.objects.filter(conversation=conversation, recipient_actor=actor)
    if read_through is not None:
        incoming_qs = incoming_qs.filter(created_at__lte=read_through)

    latest_incoming = incoming_qs.order_by("created_at", "id").last()
    if latest_incoming is None:
        return None

    if participant.last_read_at is None or participant.last_read_at < latest_incoming.created_at:
        participant.last_read_at = latest_incoming.created_at
        participant.save(update_fields=["last_read_at", "updated_at"])

    incoming_qs.filter(read_at__isnull=True).update(read_at=timezone.now())
    return latest_incoming.created_at


def require_private_messages_enabled() -> None:
    if not is_private_messages_enabled():
        raise ImproperlyConfigured("Private messaging is disabled by FEATURE_PM_E2E_ENABLED.")


def create_direct_conversation(*, created_by, participant_a, participant_b) -> Conversation:
    require_private_messages_enabled()
    if participant_a == participant_b:
        raise ValidationError("Direct conversation requires two distinct participants.")

    direct_participant_key = canonical_direct_participant_key(participant_a, participant_b)
    with transaction.atomic():
        conversation = Conversation.objects.create(
            created_by=created_by,
            conversation_type=Conversation.ConversationType.DIRECT,
            direct_participant_key=direct_participant_key,
        )
        ConversationParticipant.objects.create(conversation=conversation, actor=participant_a)
        ConversationParticipant.objects.create(conversation=conversation, actor=participant_b)
    return conversation


def get_or_create_direct_conversation(*, created_by, participant_a, participant_b) -> tuple[Conversation, bool]:
    require_private_messages_enabled()
    if participant_a == participant_b:
        raise ValidationError("Direct conversation requires two distinct participants.")

    direct_participant_key = canonical_direct_participant_key(participant_a, participant_b)
    with transaction.atomic():
        existing = (
            Conversation.objects.select_for_update()
            .filter(
                conversation_type=Conversation.ConversationType.DIRECT,
                direct_participant_key=direct_participant_key,
            )
            .first()
        )
        if existing is not None:
            return existing, False

        # Backward-compatible lookup for older direct threads created before
        # canonical participant keys existed.
        existing = (
            Conversation.objects.select_for_update()
            .filter(conversation_type=Conversation.ConversationType.DIRECT, direct_participant_key="")
            .annotate(
                participant_count=Count("participants", distinct=True),
                matched_participant_count=Count(
                    "participants__actor",
                    filter=Q(participants__actor__in=[participant_a, participant_b]),
                    distinct=True,
                ),
            )
            .filter(participant_count=2, matched_participant_count=2)
            .first()
        )
        if existing is not None:
            existing.direct_participant_key = direct_participant_key
            existing.save(update_fields=["direct_participant_key", "updated_at"])
            return existing, False

        conversation_creation_limit = max(1, int(getattr(settings, "PM_CONVERSATION_CREATION_LIMIT", 10)))
        conversation_creation_window_seconds = max(
            1,
            int(getattr(settings, "PM_CONVERSATION_CREATION_WINDOW_SECONDS", 86400)),
        )
        recent_conversations = Conversation.objects.filter(
            created_by=created_by,
            created_at__gte=timezone.now() - timedelta(seconds=conversation_creation_window_seconds),
        ).count()

        if recent_conversations >= conversation_creation_limit:
            raise ValidationError(
                f"You have created {recent_conversations} conversations in the current safety window. "
                f"Please wait before creating more conversations."
            )

        try:
            with transaction.atomic():
                conversation = Conversation.objects.create(
                    created_by=created_by,
                    conversation_type=Conversation.ConversationType.DIRECT,
                    direct_participant_key=direct_participant_key,
                )
                ConversationParticipant.objects.create(conversation=conversation, actor=participant_a)
                ConversationParticipant.objects.create(conversation=conversation, actor=participant_b)
        except IntegrityError:
            existing = Conversation.objects.get(
                conversation_type=Conversation.ConversationType.DIRECT,
                direct_participant_key=direct_participant_key,
            )
            return existing, False
    return conversation, True


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
    publish_event: bool = True,
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

    envelope = EncryptedMessageEnvelope.objects.create(
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
    if publish_event:
        publish_direct_message_event(envelope)
    return envelope


def send_direct_encrypted_message(*, conversation, sender, ciphertext: str, message_nonce: str, client_message_id: str = "", publish_event: bool = True) -> EncryptedMessageEnvelope:
    require_private_messages_enabled()

    # Phase 7.1: Check if conversation is compromised
    if conversation.is_compromised():
        raise ValidationError(
            "This conversation has been marked as compromised. "
            "Messages sent to this conversation are not considered secure. "
            "Start a new conversation to reset the security context."
        )

    participants = list(conversation.participants.select_related("actor").all())
    sender_participant = next((participant for participant in participants if participant.actor_id == sender.id), None)
    if sender_participant is None:
        raise ValidationError("Sender is not a participant in this conversation.")
    if conversation.conversation_type != Conversation.ConversationType.DIRECT:
        raise ValidationError("Encrypted send flow currently supports direct conversations only.")

    recipient_participant = next((participant for participant in participants if participant.actor_id != sender.id), None)
    if recipient_participant is None:
        raise ValidationError("Direct conversation recipient could not be resolved.")

    dm_restriction_error = get_parental_dm_restriction_error(actor=sender, target_actor=recipient_participant.actor)
    if dm_restriction_error:
        raise ValidationError(dm_restriction_error)

    sender_key = UserIdentityKey.objects.filter(actor=sender, is_active=True).order_by("-created_at").first()
    recipient_key = UserIdentityKey.objects.filter(actor=recipient_participant.actor, is_active=True).order_by("-created_at").first()
    if sender_key is None or recipient_key is None:
        raise ValidationError("Both participants need active identity keys before sending encrypted messages.")

    # Phase 7.1: Verify sender's key is valid (not compromised, not revoked, not expired)
    if not sender_key.is_valid():
        raise ValidationError("Your active key is invalid (compromised or revoked). Rotate your key before sending messages.")

    # Phase 7.1: Verify recipient's key is valid
    if not recipient_key.is_valid():
        raise ValidationError(
            "Recipient's active key is invalid (compromised or revoked). "
            "Wait for recipient to rotate their key before sending messages."
        )

    # Phase 7.2: Require recipient to have acknowledged sender's current key (optional, disabled for Phase 7.1)
    # This will be a future Phase 7.2 hardening when client-side key exchange UI is ready
    # if sender_participant.acknowledged_remote_key_id != sender_key.key_id:
    #     raise ValidationError(
    #         "Recipient has not yet acknowledged your current safety key. "
    #         "They must verify your fingerprint before you can send encrypted messages."
    #     )

    return store_encrypted_message(
        conversation=conversation,
        sender=sender,
        recipient_actor=recipient_participant.actor,
        ciphertext=ciphertext,
        message_nonce=message_nonce,
        sender_key_id=sender_key.key_id,
        recipient_key_id=recipient_key.key_id,
        client_message_id=client_message_id,
        publish_event=publish_event,
    )


def store_encrypted_attachments(*, envelope: EncryptedMessageEnvelope, uploaded_files, attachment_manifest: list[dict]) -> list[EncryptedMessageAttachment]:
    if not uploaded_files:
        return []

    manifest_by_id = {
        item["client_attachment_id"]: item
        for item in attachment_manifest
    }
    attachments = []
    for uploaded in uploaded_files:
        client_attachment_id = (getattr(uploaded, "name", "") or "").rsplit(".", 1)[0].strip()
        if client_attachment_id not in manifest_by_id:
            raise ValidationError("Encrypted attachment upload does not match attachment manifest.")
        attachment = EncryptedMessageAttachment.objects.create(
            envelope=envelope,
            client_attachment_id=client_attachment_id,
            encrypted_file=uploaded,
            encrypted_size=int(getattr(uploaded, "size", 0) or 0),
        )
        attachments.append(attachment)
    if len(attachments) != len(attachment_manifest):
        raise ValidationError("Attachment upload count does not match attachment manifest.")
    return attachments


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


def validate_public_key_format(*, public_key: str, algorithm: str = "ed25519") -> None:
    """Validate public key format based on algorithm. Enforce minimum length and structure."""
    from base64 import b64decode

    public_key = (public_key or "").strip()
    if not public_key:
        raise ValidationError("public_key cannot be empty.")

    # Check for reasonable length (32+ bytes for ED25519, 32+ for CURVE25519)
    try:
        if public_key.startswith("local-bootstrap:"):
            # Allow local bootstrap keys for development
            if len(public_key) < 20:
                raise ValidationError("Bootstrap public_key is too short.")
        else:
            # Expect base64-encoded key (decode and check length)
            # Note: Allow shorter keys for testing/development
            try:
                decoded = b64decode(public_key, validate=True)
                min_key_bytes = max(1, int(getattr(settings, "PM_PUBLIC_KEY_MIN_BYTES", 8)))
                if len(decoded) < min_key_bytes:
                    raise ValidationError(
                        f"Public key is too short ({len(decoded)} bytes). Expected >= {min_key_bytes} bytes."
                    )
            except TypeError as e:
                raise ValidationError(f"Public key must be valid base64: {str(e)}")
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Invalid public_key format: {str(e)}")


def check_rotation_cooldown(*, actor) -> None:
    """Enforce minimum cooldown period between key rotations to prevent abuse."""
    rotation_cooldown_seconds = max(1, int(getattr(settings, "PM_KEY_ROTATION_COOLDOWN_SECONDS", 300)))
    recent_rotation = (
        UserIdentityKey.objects.filter(actor=actor, rotated_at__isnull=False)
        .order_by("-rotated_at")
        .first()
    )

    if recent_rotation and recent_rotation.rotated_at:
        elapsed = timezone.now() - recent_rotation.rotated_at
        cooldown_window = timedelta(seconds=rotation_cooldown_seconds)
        if elapsed < cooldown_window:
            remaining = cooldown_window - elapsed
            raise ValidationError(
                f"Please wait {max(1, int(remaining.total_seconds()))} seconds before rotating keys again. "
                f"This helps prevent abuse of the key rotation system."
            )


def audit_key_event(*, actor, event_type: str, key=None, reason: str = "", triggered_by: str = "user_action", conversation_id=None) -> None:
    """Log key lifecycle events for audit trail and security investigation."""
    from apps.private_messages.models import KeyLifecycleAuditLog

    try:
        KeyLifecycleAuditLog.objects.create(
            actor=actor,
            key=key,
            event_type=event_type,
            reason=reason,
            triggered_by=triggered_by,
            related_conversation_id=conversation_id,
        )
    except Exception as e:
        # Log audit events are best-effort; don't block operations if audit fails
        import logging
        logger = logging.getLogger("apps.private_messages")
        logger.warning(f"Failed to log key lifecycle event: {str(e)}")


def register_browser_identity_key(*, actor, key_id: str, public_key: str, fingerprint_hex: str) -> tuple[UserIdentityKey, bool]:
    """Register a browser-generated public identity key and rotate previous active keys.

    The browser retains the private key locally; server stores only public key metadata.
    """

    require_private_messages_enabled()
    
    # Phase 7.1: Validate public key format and enforce rotation cooldown
    validate_public_key_format(public_key=public_key)
    check_rotation_cooldown(actor=actor)
    
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
                audit_key_event(actor=actor, event_type="activated", key=existing, reason="Reactivated previously rotated key")
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
