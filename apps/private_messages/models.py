import uuid

from django.db import models

from apps.core.models import TimeStampedModel


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
    title = models.CharField(max_length=255, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["conversation_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Conversation<{self.id}>"


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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey("actors.Actor", on_delete=models.CASCADE, related_name="identity_keys")
    key_id = models.CharField(max_length=128, unique=True)
    public_key = models.TextField()
    algorithm = models.CharField(max_length=32, choices=Algorithm.choices, default=Algorithm.ED25519)
    fingerprint_hex = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "is_active"]),
            models.Index(fields=["fingerprint_hex"]),
        ]

    def __str__(self) -> str:
        return f"UserIdentityKey<{self.actor.pk}:{self.key_id}>"


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
