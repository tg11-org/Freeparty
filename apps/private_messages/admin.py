from django.contrib import admin

from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageEnvelope, UserIdentityKey, PMRolloutPolicy, KeyLifecycleAuditLog


class ImmutableAdminMixin:
    """Admin mixin for write-protected records that should never be edited manually."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PMRolloutPolicy)
class PMRolloutPolicyAdmin(admin.ModelAdmin):
    list_display = ("stage", "allowlisted_count", "created_at", "updated_at")
    fieldsets = (
        ("Rollout Stage", {"fields": ("stage",)}),
        ("Allowlisted Actors", {"fields": ("allowlisted_actors",), "classes": ("wide",)}),
        ("Notes", {"fields": ("notes",), "classes": ("wide",)}),
    )

    def allowlisted_count(self, obj):
        return obj.allowlisted_actors.count()

    allowlisted_count.short_description = "Allowlisted Actors"

    def has_add_permission(self, request):
        return PMRolloutPolicy.objects.count() == 0

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KeyLifecycleAuditLog)
class KeyLifecycleAuditLogAdmin(ImmutableAdminMixin, admin.ModelAdmin):
    list_display = ("actor", "event_type", "key", "triggered_by", "created_at")
    list_filter = ("event_type", "triggered_by", "created_at")
    search_fields = ("actor__handle", "key__key_id", "reason")
    readonly_fields = (
        "id",
        "actor",
        "key",
        "event_type",
        "reason",
        "triggered_by",
        "related_conversation_id",
        "created_at",
        "updated_at",
    )


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
    list_display = ("actor", "key_id", "algorithm", "is_active", "is_compromised", "expires_at", "created_at")
    list_filter = ("algorithm", "is_active", "is_compromised", "created_at")
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
        "is_compromised",
        "compromised_at",
        "compromised_reason",
        "expires_at",
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
