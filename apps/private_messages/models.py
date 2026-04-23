import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def encrypted_dm_attachment_upload_to(instance: "EncryptedMessageAttachment", filename: str) -> str:
    return f"dm_attachments/{instance.envelope.conversation_id}/{instance.envelope_id}/{filename}"


class Conversation(TimeStampedModel):
    class ConversationType(models.TextChoices):
        DIRECT = "direct", "Direct"
        GROUP = "group", "Group"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        "actors.Actor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_conversations",
    )
    conversation_type = models.CharField(max_length=16, choices=ConversationType.choices, default=ConversationType.DIRECT)
    direct_participant_key = models.CharField(max_length=80, blank=True, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    compromised_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when conversation is suspected compromised; invalidates prior messages",
    )
    compromise_reason = models.TextField(blank=True, help_text="Description of compromise incident")

    class Meta(TimeStampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["conversation_type", "created_at"]),
            models.Index(fields=["compromised_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["direct_participant_key"],
                condition=~models.Q(direct_participant_key=""),
                name="uniq_direct_conversation_participant_key",
            ),
        ]

    def __str__(self) -> str:
        return f"Conversation<{self.id}>"

    def is_compromised(self) -> bool:
        """Check if conversation has been marked as compromised."""
        return self.compromised_at is not None


class ConversationParticipant(TimeStampedModel):
    class ParticipantState(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"
        REMOVED = "removed", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("private_messages.Conversation", on_delete=models.CASCADE, related_name="participants")
    actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="dm_participations")
    participant_state = models.CharField(max_length=16, choices=ParticipantState.choices, default=ParticipantState.ACTIVE)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    acknowledged_remote_key_id = models.CharField(max_length=128, blank=True)
    acknowledged_remote_key_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "actor"], name="uniq_conversation_actor"),
        ]
        indexes = [
            models.Index(fields=["actor", "participant_state"]),
            models.Index(fields=["conversation", "participant_state"]),
        ]

    def __str__(self) -> str:
        return f"ConversationParticipant<{self.conversation.pk}:{self.actor.pk}>"


class UserIdentityKey(TimeStampedModel):
    class Algorithm(models.TextChoices):
        ED25519 = "ed25519", "Ed25519"
        CURVE25519 = "curve25519", "Curve25519"

    class CreationSource(models.TextChoices):
        BOOTSTRAP = "bootstrap", "Bootstrap"
        BROWSER = "browser", "Browser"
        FEDERATION = "federation", "Federation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="identity_keys")
    key_id = models.CharField(max_length=128, unique=True)
    public_key = models.TextField()
    algorithm = models.CharField(max_length=32, choices=Algorithm.choices, default=Algorithm.ED25519)
    fingerprint_hex = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    is_compromised = models.BooleanField(default=False, help_text="Mark as True if key is suspected compromised")
    compromised_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when compromise was detected")
    compromised_reason = models.TextField(blank=True, help_text="Description of compromise reason/incident")
    revoked_at = models.DateTimeField(null=True, blank=True, help_text="Set when key is revoked")
    revocation_reason = models.TextField(blank=True, help_text="Reason for key revocation")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Key expiration timestamp for auto-invalidation")
    rotation_cooldown_until = models.DateTimeField(null=True, blank=True, help_text="Prevent spam: timestamp after which next rotation is allowed")
    creation_source = models.CharField(
        max_length=32,
        default=CreationSource.BOOTSTRAP,
        choices=CreationSource.choices,
        help_text="Origin of key: bootstrap (dev), browser (prod), or federation",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "is_active"]),
            models.Index(fields=["fingerprint_hex"]),
            models.Index(fields=["actor", "is_compromised"]),
            models.Index(fields=["actor", "revoked_at"]),
        ]

    def __str__(self) -> str:
        return f"UserIdentityKey<{self.actor.pk}:{self.key_id}>"

    def is_valid(self) -> bool:
        """Check if key is currently valid for use (not compromised, not expired, not rotated out, not revoked)."""
        if self.is_compromised:
            return False
        if self.revoked_at is not None:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return self.is_active

    def can_rotate(self) -> bool:
        """Check if key can be rotated (not in cooldown period)."""
        if self.rotation_cooldown_until is None:
            return True
        return timezone.now() >= self.rotation_cooldown_until


class KeyLifecycleAuditLog(TimeStampedModel):
    """Audit trail for all key lifecycle events (creation, rotation, compromise marking, expiration)."""

    class EventType(models.TextChoices):
        CREATED = "created", "Key Created"
        ROTATED = "rotated", "Key Rotated"
        ACTIVATED = "activated", "Key Activated"
        DEACTIVATED = "deactivated", "Key Deactivated"
        MARKED_COMPROMISED = "marked_compromised", "Marked as Compromised"
        UNMARKED_COMPROMISED = "unmarked_compromised", "Compromise Mark Removed"
        EXPIRED = "expired", "Key Expired"
        ACKNOWLEDGED = "acknowledged", "Key Acknowledged in Conversation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="key_audit_logs")
    key = models.ForeignKey("UserIdentityKey", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    reason = models.TextField(blank=True, help_text="Reason for the event (e.g., rotation reason, compromise details)")
    triggered_by = models.CharField(
        max_length=64,
        choices=[("user_action", "User Action"), ("system", "System"), ("abuse_detection", "Abuse Detection")],
        default="user_action",
    )
    related_conversation_id = models.UUIDField(null=True, blank=True, help_text="Conversation ID if applicable")

    class Meta(TimeStampedModel.Meta):
        ordering = ["-created_at"]
        verbose_name_plural = "Key Lifecycle Audit Logs"
        indexes = [
            models.Index(fields=["actor", "event_type", "created_at"]),
            models.Index(fields=["key", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"KeyLifecycleAuditLog<{self.actor.pk}:{self.event_type}>"


class PMRolloutPolicy(TimeStampedModel):
    """Control staged rollout of PM feature by actor, cohort, or environment."""

    class RolloutStage(models.TextChoices):
        DISABLED = "disabled", "Disabled (Feature Flag Off)"
        ALLOWLIST = "allowlist", "Allowlist (Explicit Per-Actor)"
        BETA = "beta", "Beta (Opt-In)"
        GENERAL = "general", "General Availability"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stage = models.CharField(max_length=16, choices=RolloutStage.choices, default=RolloutStage.DISABLED)
    allowlisted_actors = models.ManyToManyField(
        "actors.Actor", blank=True, related_name="pm_allowlisted", help_text="Only applies when stage=ALLOWLIST"
    )
    notes = models.TextField(blank=True, help_text="Internal notes on rollout rationale and milestones")

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "PM Rollout Policies"

    def __str__(self) -> str:
        return f"PMRolloutPolicy<stage={self.stage}>"

    @staticmethod
    def get_default_instance():
        """Get or create the singleton PM rollout policy instance."""
        # Use a fixed UUID for the singleton instance
        singleton_id = uuid.UUID('00000000-0000-0000-0000-000000000000')
        obj, _ = PMRolloutPolicy.objects.get_or_create(pk=singleton_id)
        return obj


class EncryptedMessageEnvelope(TimeStampedModel):
    class EncryptionScheme(models.TextChoices):
        XCHACHA20POLY1305 = "xchacha20poly1305", "XChaCha20-Poly1305"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("private_messages.Conversation", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey("actors.Actor", on_delete=models.SET_NULL, null=True, blank=True, related_name="dm_sent_messages")
    recipient_actor = models.ForeignKey(
        "actors.Actor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_received_messages",
    )
    ciphertext = models.TextField()
    message_nonce = models.CharField(max_length=255)
    sender_key_id = models.CharField(max_length=128)
    recipient_key_id = models.CharField(max_length=128)
    key_epoch = models.PositiveIntegerField(default=1)
    aad_hash = models.CharField(max_length=255, blank=True)
    encryption_scheme = models.CharField(
        max_length=32,
        choices=EncryptionScheme.choices,
        default=EncryptionScheme.XCHACHA20POLY1305,
    )
    client_message_id = models.CharField(max_length=128, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sender", "client_message_id"],
                condition=~models.Q(client_message_id=""),
                name="uniq_client_message_per_sender",
            ),
        ]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["recipient_actor", "created_at"]),
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"EncryptedMessageEnvelope<{self.id}>"


class EncryptedMessageAttachment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    envelope = models.ForeignKey("private_messages.EncryptedMessageEnvelope", on_delete=models.CASCADE, related_name="attachments")
    client_attachment_id = models.CharField(max_length=128)
    encrypted_file = models.FileField(upload_to=encrypted_dm_attachment_upload_to)
    encrypted_size = models.PositiveBigIntegerField(default=0)

    class Meta(TimeStampedModel.Meta):
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["envelope", "client_attachment_id"], name="uniq_dm_attachment_client_id_per_envelope"),
        ]
        indexes = [
            models.Index(fields=["envelope", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"EncryptedMessageAttachment<{self.id}>"
