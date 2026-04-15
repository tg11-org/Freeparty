from django.contrib import admin

from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageEnvelope, UserIdentityKey


class ImmutableAdminMixin:
    """Admin mixin for write-protected records that should never be edited manually."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(ImmutableAdminMixin, admin.ModelAdmin):
    list_display = ("id", "conversation_type", "created_by", "created_at")
    list_filter = ("conversation_type", "created_at")
    search_fields = ("id", "created_by__handle")
    readonly_fields = ("id", "created_by", "conversation_type", "title", "created_at", "updated_at")


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(ImmutableAdminMixin, admin.ModelAdmin):
    list_display = ("conversation", "actor", "participant_state", "joined_at", "left_at")
    list_filter = ("participant_state", "joined_at")
    search_fields = ("conversation__id", "actor__handle")
    readonly_fields = (
        "id",
        "conversation",
        "actor",
        "participant_state",
        "joined_at",
        "left_at",
        "acknowledged_remote_key_id",
        "acknowledged_remote_key_at",
        "created_at",
        "updated_at",
    )


@admin.register(UserIdentityKey)
class UserIdentityKeyAdmin(ImmutableAdminMixin, admin.ModelAdmin):
    list_display = ("actor", "key_id", "algorithm", "is_active", "created_at")
    list_filter = ("algorithm", "is_active")
    search_fields = ("actor__handle", "key_id", "fingerprint_hex")
    readonly_fields = (
        "id",
        "actor",
        "key_id",
        "public_key",
        "algorithm",
        "fingerprint_hex",
        "is_active",
        "rotated_at",
        "created_at",
        "updated_at",
    )


@admin.register(EncryptedMessageEnvelope)
class EncryptedMessageEnvelopeAdmin(ImmutableAdminMixin, admin.ModelAdmin):
    list_display = (
        "conversation",
        "sender",
        "recipient_actor",
        "encryption_scheme",
        "key_epoch",
        "created_at",
        "delivered_at",
        "read_at",
    )
    list_filter = ("encryption_scheme", "created_at", "delivered_at", "read_at")
    search_fields = ("conversation__id", "sender__handle", "recipient_actor__handle", "client_message_id")
    readonly_fields = (
        "id",
        "conversation",
        "sender",
        "recipient_actor",
        "ciphertext",
        "message_nonce",
        "sender_key_id",
        "recipient_key_id",
        "key_epoch",
        "aad_hash",
        "encryption_scheme",
        "client_message_id",
        "delivered_at",
        "read_at",
        "created_at",
        "updated_at",
    )
