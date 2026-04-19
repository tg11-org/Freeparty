from datetime import timedelta
import json

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from apps.accounts.models import User
from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageAttachment, EncryptedMessageEnvelope, UserIdentityKey, PMRolloutPolicy
from apps.private_messages.consumers import DirectMessageConsumer
from apps.private_messages.routing import websocket_urlpatterns
from apps.private_messages.security import (
    canonical_safety_fingerprint_input,
    has_remote_key_changed,
    compute_identicon_seed,
    compute_safety_fingerprint_hex,
)
from apps.private_messages.services import (
    create_direct_conversation,
    get_or_create_direct_conversation,
    send_direct_encrypted_message,
    serialize_encrypted_envelope,
    store_encrypted_message,
)


@override_settings(FEATURE_PM_E2E_ENABLED=True)
class PrivateMessagesModelTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-pm@example.com", username="alicepm", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-pm@example.com", username="bobpm", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()

    def test_conversation_participant_unique_constraint(self):
        conversation = Conversation.objects.create(created_by=self.alice.actor)
        ConversationParticipant.objects.create(conversation=conversation, actor=self.alice.actor)
        with self.assertRaises(IntegrityError):
            ConversationParticipant.objects.create(conversation=conversation, actor=self.alice.actor)

    def test_store_encrypted_message_persists_envelope(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="base64:ciphertext",
            message_nonce="base64:nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            key_epoch=1,
            aad_hash="sha256:abcd",
            client_message_id="client-msg-1",
        )

        self.assertEqual(envelope.conversation, conversation)
        self.assertEqual(envelope.sender, self.alice.actor)
        self.assertEqual(envelope.recipient_actor, self.bob.actor)
        self.assertEqual(envelope.ciphertext, "base64:ciphertext")

    def test_store_encrypted_message_rejects_blank_ciphertext(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

        with self.assertRaises(ValidationError):
            store_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor,
                recipient_actor=self.bob.actor,
                ciphertext="",
                message_nonce="base64:nonce",
                sender_key_id="alice-key-1",
                recipient_key_id="bob-key-1",
            )

    @override_settings(FEATURE_PM_WEBSOCKET_ENABLED=True)
    @patch("apps.private_messages.services.get_channel_layer")
    def test_store_encrypted_message_publishes_websocket_event_when_enabled(self, mocked_get_channel_layer):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

        class DummyLayer:
            def __init__(self):
                self.sent = []

            async def group_send(self, group_name, payload):
                self.sent.append((group_name, payload))

        layer = DummyLayer()
        mocked_get_channel_layer.return_value = layer

        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="base64:ciphertext",
            message_nonce="base64:nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-msg-ws-1",
        )

        self.assertEqual(len(layer.sent), 1)
        group_name, payload = layer.sent[0]
        self.assertEqual(group_name, f"dm_conversation_{conversation.id}")
        self.assertEqual(payload["type"], "dm_envelope")
        self.assertEqual(payload["payload"]["envelope"]["id"], str(envelope.id))

    @override_settings(FEATURE_PM_WEBSOCKET_ENABLED=True)
    @patch("apps.private_messages.services.get_channel_layer")
    def test_websocket_broadcast_payload_matches_poll_serialization(self, mocked_get_channel_layer):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

        class DummyLayer:
            def __init__(self):
                self.sent = []

            async def group_send(self, group_name, payload):
                self.sent.append((group_name, payload))

        layer = DummyLayer()
        mocked_get_channel_layer.return_value = layer

        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="base64:ciphertext",
            message_nonce="base64:nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-msg-ws-2",
        )
        self.assertEqual(serialize_encrypted_envelope(envelope)["id"], str(envelope.id))


@override_settings(
    FEATURE_PM_E2E_ENABLED=True,
    FEATURE_PM_WEBSOCKET_ENABLED=True,
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class PrivateMessagesWebsocketConsumerTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-pm-ws@example.com", username="alicepmws", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-pm-ws@example.com", username="bobpmws", password="secret123")  # type: ignore[attr-defined]
        self.eve = User.objects.create_user(email="eve-pm-ws@example.com", username="evepmws", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()
        self.eve.mark_email_verified()
        self.conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

    async def _connect_async(self, user, conversation_id=None):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(
            application,
            f"/ws/messages/{conversation_id or self.conversation.id}/",
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        return communicator, connected

    def _connect(self, user, conversation_id=None):
        return async_to_sync(self._connect_async)(user, conversation_id)

    def test_participant_can_connect_and_receive_ready_event(self):
        async def runner():
            communicator, connected = await self._connect_async(self.alice)
            self.assertTrue(connected)
            payload = await communicator.receive_json_from()
            await communicator.disconnect()
            return payload

        payload = async_to_sync(runner)()
        self.assertEqual(payload["type"], "dm.socket.ready")
        self.assertEqual(payload["conversation_id"], str(self.conversation.id))

    def test_non_participant_is_rejected(self):
        communicator, connected = self._connect(self.eve)
        self.assertFalse(connected)

    def test_socket_receives_dm_envelope_event(self):
        async def runner():
            communicator, connected = await self._connect_async(self.alice)
            self.assertTrue(connected)
            await communicator.receive_json_from()  # ready event
            await sync_to_async(store_encrypted_message)(
                conversation=self.conversation,
                sender=self.bob.actor,
                recipient_actor=self.alice.actor,
                ciphertext="cipher-live",
                message_nonce="nonce-live",
                sender_key_id="bob-key-1",
                recipient_key_id="alice-key-1",
                client_message_id="client-live-1",
            )
            payload = await communicator.receive_json_from()
            await communicator.disconnect()
            return payload

        payload = async_to_sync(runner)()
        self.assertEqual(payload["type"], "dm.envelope")
        self.assertEqual(payload["envelope"]["ciphertext"], "cipher-live")


@override_settings(FEATURE_PM_E2E_ENABLED=False)
class PrivateMessagesFeatureFlagTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-pm-flag@example.com", username="alicepmflag", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-pm-flag@example.com", username="bobpmflag", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()

    def test_create_direct_conversation_blocked_when_feature_disabled(self):
        with self.assertRaises(ImproperlyConfigured):
            create_direct_conversation(
                created_by=self.alice.actor,
                participant_a=self.alice.actor,
                participant_b=self.bob.actor,
            )

    def test_store_message_blocked_when_feature_disabled(self):
        conversation = Conversation.objects.create(created_by=self.alice.actor)
        with self.assertRaises(ImproperlyConfigured):
            store_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor,
                recipient_actor=self.bob.actor,
                ciphertext="base64:ciphertext",
                message_nonce="base64:nonce",
                sender_key_id="alice-key-1",
                recipient_key_id="bob-key-1",
            )


@override_settings(FEATURE_PM_E2E_ENABLED=True)
class PMRolloutPolicyStagedAccessTests(TestCase):
    """Test staged PM rollout via PMRolloutPolicy stages."""

    def setUp(self):
        self.alice = User.objects.create_user(email="alice-rollout@example.com", username="alice_rollout", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-rollout@example.com", username="bob_rollout", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()
        self.policy = PMRolloutPolicy.get_default_instance()

    def test_disabled_stage_blocks_all_actors(self):
        """When stage=DISABLED, no actors can use PM."""
        self.policy.stage = PMRolloutPolicy.RolloutStage.DISABLED
        self.policy.save()

        from apps.private_messages.services import is_actor_pm_eligible

        self.assertFalse(is_actor_pm_eligible(actor=self.alice.actor))
        self.assertFalse(is_actor_pm_eligible(actor=self.bob.actor))

    def test_allowlist_stage_allows_only_listed_actors(self):
        """When stage=ALLOWLIST, only allowlisted actors can use PM."""
        from apps.private_messages.services import is_actor_pm_eligible

        self.policy.stage = PMRolloutPolicy.RolloutStage.ALLOWLIST
        self.policy.save()

        # Alice not allowlisted yet
        self.assertFalse(is_actor_pm_eligible(actor=self.alice.actor))

        # Add Alice to allowlist
        self.policy.allowlisted_actors.add(self.alice.actor)
        self.policy.save()

        # Alice can use PM now
        self.assertTrue(is_actor_pm_eligible(actor=self.alice.actor))
        # Bob not in allowlist
        self.assertFalse(is_actor_pm_eligible(actor=self.bob.actor))

    def test_beta_stage_allows_all_actors(self):
        """When stage=BETA, all authenticated actors can use PM."""
        from apps.private_messages.services import is_actor_pm_eligible

        self.policy.stage = PMRolloutPolicy.RolloutStage.BETA
        self.policy.save()

        self.assertTrue(is_actor_pm_eligible(actor=self.alice.actor))
        self.assertTrue(is_actor_pm_eligible(actor=self.bob.actor))

    def test_general_stage_allows_all_actors(self):
        """When stage=GENERAL, all authenticated actors can use PM."""
        from apps.private_messages.services import is_actor_pm_eligible

        self.policy.stage = PMRolloutPolicy.RolloutStage.GENERAL
        self.policy.save()

        self.assertTrue(is_actor_pm_eligible(actor=self.alice.actor))
        self.assertTrue(is_actor_pm_eligible(actor=self.bob.actor))

    def test_feature_flag_override_disables_all_stages(self):
        """When FEATURE_PM_E2E_ENABLED=False, all stages deny access."""
        from apps.private_messages.services import is_actor_pm_eligible

        self.policy.stage = PMRolloutPolicy.RolloutStage.GENERAL
        self.policy.allowlisted_actors.add(self.alice.actor)
        self.policy.save()

        # When feature flag is on, both work
        self.assertTrue(is_actor_pm_eligible(actor=self.alice.actor))
        self.assertTrue(is_actor_pm_eligible(actor=self.bob.actor))

        # With flag off (via decorator), both denied
        with override_settings(FEATURE_PM_E2E_ENABLED=False):
            self.assertFalse(is_actor_pm_eligible(actor=self.alice.actor))
            self.assertFalse(is_actor_pm_eligible(actor=self.bob.actor))


class SafetyFingerprintContractTests(TestCase):
    def test_canonical_input_is_order_invariant(self):
        a = canonical_safety_fingerprint_input(" AA BB ", "ccdd")
        b = canonical_safety_fingerprint_input("ccdd", "aabb")
        self.assertEqual(a, b)

    def test_safety_fingerprint_hex_is_deterministic(self):
        first = compute_safety_fingerprint_hex("alice-key-fp", "bob-key-fp")
        second = compute_safety_fingerprint_hex("alice-key-fp", "bob-key-fp")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_safety_fingerprint_hex_is_order_invariant(self):
        first = compute_safety_fingerprint_hex("alice-key-fp", "bob-key-fp")
        second = compute_safety_fingerprint_hex("bob-key-fp", "alice-key-fp")
        self.assertEqual(first, second)

    def test_identicon_seed_is_deterministic_prefix_contract(self):
        fp = compute_safety_fingerprint_hex("alice-key-fp", "bob-key-fp")
        seed = compute_identicon_seed("alice-key-fp", "bob-key-fp")
        self.assertEqual(seed, fp[:32])
        self.assertEqual(len(seed), 32)

    def test_remote_key_change_detects_unacknowledged_key_id(self):
        self.assertTrue(has_remote_key_changed(acknowledged_remote_key_id="old-key", remote_key_id="new-key"))
        self.assertFalse(has_remote_key_changed(acknowledged_remote_key_id="same-key", remote_key_id="same-key"))


@override_settings(FEATURE_PM_E2E_ENABLED=True)
class PrivateMessagesHtmlFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(email="alice-dm@example.com", username="alicedm", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-dm@example.com", username="bobdm", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()

    def test_start_direct_conversation_from_actor_profile(self):
        self.client.force_login(self.alice)
        response = self.client.post(f"/messages/start/{self.bob.actor.handle}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_start_direct_conversation_reuses_existing_direct_thread(self):
        self.client.force_login(self.alice)
        first = self.client.post(f"/messages/start/{self.bob.actor.handle}/")
        second = self.client.post(f"/messages/start/{self.bob.actor.handle}/")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_messages_list_renders(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-list-key",
            public_key="alice-list-public-key",
            fingerprint_hex="c" * 64,
        )
        self.client.force_login(self.alice)
        response = self.client.get("/messages/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/messages/{conversation.id}/")
        self.assertContains(response, f"@{self.bob.actor.handle}")

    def test_messages_list_is_paginated(self):
        for idx in range(21):
            other = User.objects.create_user(
                email=f"page-{idx}@example.com",
                username=f"page{idx}",
                password="secret123",
            )
            other.mark_email_verified()
            create_direct_conversation(
                created_by=self.alice.actor,
                participant_a=self.alice.actor,
                participant_b=other.actor,
            )

        self.client.force_login(self.alice)
        response = self.client.get("/messages/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertEqual(len(response.context["conversations"]), 20)

    def test_messages_list_can_filter_unread_threads(self):
        unread_conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        other = User.objects.create_user(email="clear-thread@example.com", username="clearthread", password="secret123")
        other.mark_email_verified()
        read_conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=other.actor,
        )
        store_encrypted_message(
            conversation=unread_conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="unread-cipher",
            message_nonce="unread-nonce",
            sender_key_id="bob-unread-key",
            recipient_key_id="alice-unread-key",
            client_message_id="client-unread",
        )
        read_message = store_encrypted_message(
            conversation=read_conversation,
            sender=other.actor,
            recipient_actor=self.alice.actor,
            ciphertext="read-cipher",
            message_nonce="read-nonce",
            sender_key_id="other-read-key",
            recipient_key_id="alice-read-key",
            client_message_id="client-read",
        )
        participant = ConversationParticipant.objects.get(conversation=read_conversation, actor=self.alice.actor)
        participant.last_read_at = read_message.created_at
        participant.save(update_fields=["last_read_at", "updated_at"])

        self.client.force_login(self.alice)
        response = self.client.get("/messages/?filter=unread")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filter_type"], "unread")
        ids = {conversation.id for conversation in response.context["conversations"]}
        self.assertIn(unread_conversation.id, ids)
        self.assertNotIn(read_conversation.id, ids)

    def test_messages_list_offers_bootstrap_when_local_key_missing(self):
        self.client.force_login(self.alice)
        response = self.client.get("/messages/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate my identity key")

    def test_bootstrap_identity_key_creates_active_key(self):
        self.client.force_login(self.alice)
        response = self.client.post("/messages/keys/bootstrap/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserIdentityKey.objects.filter(actor=self.alice.actor, is_active=True).exists())

    def test_detail_bootstrap_returns_to_conversation(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            "/messages/keys/bootstrap/",
            {"next": f"/messages/{conversation.id}/"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/messages/{conversation.id}/", response["Location"])

    def test_conversation_detail_shows_send_block_reason_without_keys(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Both participants need active identity keys")

    def test_conversation_detail_marks_incoming_messages_as_read(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="read-on-open",
            message_nonce="read-on-open-nonce",
            sender_key_id="bob-read-key",
            recipient_key_id="alice-read-key",
            client_message_id="client-read-open",
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")

        self.assertEqual(response.status_code, 200)
        participant = ConversationParticipant.objects.get(conversation=conversation, actor=self.alice.actor)
        envelope.refresh_from_db()
        self.assertEqual(participant.last_read_at, envelope.created_at)
        self.assertIsNotNone(envelope.read_at)

    def test_send_encrypted_message_stores_envelope_when_keys_exist(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
        )

        self.client.force_login(self.alice)
        response = self.client.post(
            f"/messages/{conversation.id}/send/",
            {
                "ciphertext": "base64:encrypted-payload",
                "message_nonce": "nonce-123",
                "client_message_id": "client-1",
            },
        )
        self.assertEqual(response.status_code, 302)
        envelope = EncryptedMessageEnvelope.objects.get(conversation=conversation)
        self.assertEqual(envelope.sender, self.alice.actor)
        self.assertEqual(envelope.recipient_actor, self.bob.actor)
        self.assertEqual(envelope.sender_key_id, "alice-key-1")
        self.assertEqual(envelope.recipient_key_id, "bob-key-1")

    def test_send_encrypted_message_stores_encrypted_attachment(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
        )

        upload = SimpleUploadedFile("attach-1.bin", b"encrypted-blob", content_type="application/octet-stream")
        self.client.force_login(self.alice)
        response = self.client.post(
            f"/messages/{conversation.id}/send/",
            {
                "ciphertext": "base64:encrypted-payload",
                "message_nonce": "nonce-123",
                "client_message_id": "client-attachment-1",
                "attachment_manifest": json.dumps([
                    {
                        "client_attachment_id": "attach-1",
                        "encrypted_size": len(b"encrypted-blob"),
                    }
                ]),
                "encrypted_attachments": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        envelope = EncryptedMessageEnvelope.objects.get(conversation=conversation)
        attachment = EncryptedMessageAttachment.objects.get(envelope=envelope)
        self.assertEqual(attachment.client_attachment_id, "attach-1")
        self.assertEqual(attachment.encrypted_size, len(b"encrypted-blob"))

    def test_download_encrypted_attachment_requires_conversation_participant(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="base64:ciphertext",
            message_nonce="base64:nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-msg-attachment-download",
        )
        attachment = EncryptedMessageAttachment.objects.create(
            envelope=envelope,
            client_attachment_id="attach-download-1",
            encrypted_file=SimpleUploadedFile("attach-download-1.bin", b"encrypted-blob", content_type="application/octet-stream"),
            encrypted_size=len(b"encrypted-blob"),
        )

        eve = User.objects.create_user(email="eve-pm-download@example.com", username="evepmdl", password="secret123")
        eve.mark_email_verified()
        self.client.force_login(eve)
        response = self.client.get(f"/messages/{conversation.id}/attachments/{attachment.id}/download/")
        self.assertEqual(response.status_code, 404)

    def test_conversation_updates_endpoint_returns_new_envelopes_after_marker(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )

        first = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="first-cipher",
            message_nonce="first-nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-1",
        )
        second = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="second-cipher",
            message_nonce="second-nonce",
            sender_key_id="bob-key-1",
            recipient_key_id="alice-key-1",
            client_message_id="client-2",
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/updates/?after={first.created_at.isoformat()}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["envelopes"]), 1)
        ordered = list(
            EncryptedMessageEnvelope.objects.filter(id__in=[first.id, second.id]).order_by("created_at", "id")
        )
        self.assertEqual(payload["envelopes"][0]["id"], str(ordered[1].id))
        self.assertIn("alice-key-1", payload["public_keys_by_key_id"])
        self.assertIn("bob-key-1", payload["public_keys_by_key_id"])

    def test_conversation_updates_endpoint_returns_next_cursor(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        latest = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="second-cipher",
            message_nonce="second-nonce",
            sender_key_id="bob-key-1",
            recipient_key_id="alice-key-1",
            client_message_id="client-2",
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/updates/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["next_cursor"].endswith(f"|{latest.id}"))

    def test_conversation_updates_endpoint_emits_success_metric_log(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-metric-key-1",
            public_key="alice-metric-public-key",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-metric-key-1",
            public_key="bob-metric-public-key",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="metric-cipher",
            message_nonce="metric-nonce",
            sender_key_id="bob-metric-key-1",
            recipient_key_id="alice-metric-key-1",
            client_message_id="metric-client-1",
        )

        self.client.force_login(self.alice)
        with self.assertLogs("apps.core.services.interaction_observability", level="INFO") as logs:
            response = self.client.get(f"/messages/{conversation.id}/updates/")
        self.assertEqual(response.status_code, 200)
        joined = "\n".join(logs.output)
        self.assertIn("interaction_metric", joined)
        self.assertIn("name=dm_conversation_updates", joined)
        self.assertIn("success=True", joined)

    def test_conversation_updates_endpoint_uses_cursor_tiebreak_for_same_timestamp(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        first = store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="first-cipher",
            message_nonce="first-nonce",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-1",
        )
        second = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="second-cipher",
            message_nonce="second-nonce",
            sender_key_id="bob-key-1",
            recipient_key_id="alice-key-1",
            client_message_id="client-2",
        )
        EncryptedMessageEnvelope.objects.filter(id__in=[first.id, second.id]).update(created_at=first.created_at)
        ordered = list(
            EncryptedMessageEnvelope.objects.filter(id__in=[first.id, second.id]).order_by("created_at", "id")
        )
        cursor = f"{ordered[0].created_at.isoformat()}|{ordered[0].id}"

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/updates/?cursor={cursor}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["envelopes"]), 1)
        self.assertEqual(payload["envelopes"][0]["id"], str(ordered[1].id))

    def test_conversation_updates_endpoint_marks_has_more_for_large_gap(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        for idx in range(101):
            store_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor if idx % 2 == 0 else self.bob.actor,
                recipient_actor=self.bob.actor if idx % 2 == 0 else self.alice.actor,
                ciphertext=f"cipher-{idx}",
                message_nonce=f"nonce-{idx}",
                sender_key_id="alice-key-1" if idx % 2 == 0 else "bob-key-1",
                recipient_key_id="bob-key-1" if idx % 2 == 0 else "alice-key-1",
                client_message_id=f"client-{idx}",
            )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/updates/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["envelopes"]), 100)
        self.assertTrue(payload["has_more"])

    def test_conversation_updates_endpoint_rejects_invalid_cursor(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )

        self.client.force_login(self.alice)
        with self.assertLogs("apps.core.services.interaction_observability", level="WARNING") as logs:
            response = self.client.get(f"/messages/{conversation.id}/updates/?cursor=not-a-real-cursor")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        joined = "\n".join(logs.output)
        self.assertIn("interaction_metric", joined)
        self.assertIn("name=dm_conversation_updates", joined)
        self.assertIn("success=False", joined)

    def test_conversation_detail_shows_key_change_warning_for_unacknowledged_remote_key(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        participant = ConversationParticipant.objects.get(conversation=conversation, actor=self.alice.actor)
        participant.acknowledged_remote_key_id = "old-bob-key"
        participant.save(update_fields=["acknowledged_remote_key_id", "updated_at"])

        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-2",
            public_key="bob-public-key-2",
            fingerprint_hex="b" * 64,
            rotated_at=None,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Key change warning")
        self.assertContains(response, "bob-key-2")

    def test_conversation_detail_shows_fingerprint_validate_button_when_contract_exists(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Validate fingerprint")
        self.assertContains(response, "validate-fingerprint-identicon")
        self.assertContains(response, 'id="toggle-fingerprint-panel"')

    def test_acknowledge_remote_key_clears_warning_contract(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-2",
            public_key="bob-public-key-2",
            fingerprint_hex="b" * 64,
        )

        self.client.force_login(self.alice)
        response = self.client.post(f"/messages/{conversation.id}/acknowledge-key/")
        self.assertEqual(response.status_code, 302)
        participant = ConversationParticipant.objects.get(conversation=conversation, actor=self.alice.actor)
        self.assertEqual(participant.acknowledged_remote_key_id, "bob-key-2")
        self.assertIsNotNone(participant.acknowledged_remote_key_at)

    @override_settings(FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=True, DEBUG=True)
    def test_conversation_detail_shows_ciphertext_preview_when_enabled(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="dev-preview-ciphertext",
            message_nonce="nonce-123",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-preview-1",
        )

        self.client.force_login(self.bob)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dev preview enabled")
        self.assertContains(response, "dev-preview-ciphertext")

    @override_settings(FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=False, DEBUG=True)
    def test_conversation_detail_hides_ciphertext_when_preview_disabled(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-key-1",
            public_key="alice-public-key",
            fingerprint_hex="a" * 64,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-key-1",
            public_key="bob-public-key",
            fingerprint_hex="b" * 64,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.alice.actor,
            recipient_actor=self.bob.actor,
            ciphertext="hidden-ciphertext",
            message_nonce="nonce-123",
            sender_key_id="alice-key-1",
            recipient_key_id="bob-key-1",
            client_message_id="client-preview-2",
        )

        self.client.force_login(self.bob)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ciphertext is not rendered in the HTML view")
        self.assertNotContains(response, "Dev preview enabled (DEBUG only)")

    def test_register_browser_identity_key_endpoint_creates_active_curve_key(self):
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-old-key",
            public_key="old-public",
            fingerprint_hex="c" * 64,
        )

        self.client.force_login(self.alice)
        response = self.client.post(
            "/messages/keys/register/",
            {
                "key_id": "web-ecdh-1234567890abcdef",
                "public_key": "MIIBSzBJBgcqhkjOPQIB",
                "fingerprint_hex": "a" * 64,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        active = UserIdentityKey.objects.get(actor=self.alice.actor, is_active=True)
        self.assertEqual(active.key_id, "web-ecdh-1234567890abcdef")
        self.assertEqual(active.algorithm, UserIdentityKey.Algorithm.CURVE25519)
        old_key = UserIdentityKey.objects.get(actor=self.alice.actor, key_id="alice-old-key")
        self.assertFalse(old_key.is_active)

    def test_register_browser_identity_key_endpoint_rejects_invalid_payload(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            "/messages/keys/register/",
            {
                "key_id": "",
                "public_key": "",
                "fingerprint_hex": "zzz",
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])

    def test_conversation_detail_browser_send_form_uses_novalidate(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-web-key",
            public_key="alice-web-public",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-web-key",
            public_key="bob-web-public",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="e2ee-send-form"')
        self.assertContains(response, "novalidate")
        self.assertContains(response, 'id="toggle-browser-e2ee-panel"')
        self.assertContains(response, 'id="browser-e2ee-panel-body"')
        self.assertContains(response, 'id="dm-live-status"')

    @override_settings(FEATURE_PM_WEBSOCKET_ENABLED=True)
    def test_conversation_detail_exposes_websocket_bootstrap_when_enabled(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pm-websocket-enabled')
        self.assertContains(response, f'/ws/messages/{conversation.id}/')
        self.assertContains(response, 'Live updates: polling')

    def test_conversation_detail_shows_device_specific_keypair_button_label(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-web-key",
            public_key="alice-web-public",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-web-key",
            public_key="bob-web-public",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate browser keypair for this device")

    def test_conversation_detail_shows_device_key_inventory_section(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-device-key-1",
            public_key="alice-device-public",
            fingerprint_hex="a" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-device-key-1",
            public_key="bob-device-public",
            fingerprint_hex="b" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Device &amp; Key Inventory")
        self.assertContains(response, "alice-device-key-1")
        self.assertContains(response, "bob-device-key-1")
        self.assertContains(response, "Acknowledged remote key id")

    def test_conversation_detail_shows_device_recovery_guidance(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-device-key-2",
            public_key="alice-device-public-2",
            fingerprint_hex="c" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )
        UserIdentityKey.objects.create(
            actor=self.bob.actor,
            key_id="bob-device-key-2",
            public_key="bob-device-public-2",
            fingerprint_hex="d" * 64,
            algorithm=UserIdentityKey.Algorithm.CURVE25519,
        )

        self.client.force_login(self.alice)
        response = self.client.get(f"/messages/{conversation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "if this browser is missing your private key")
        self.assertContains(response, "re-verify the safety fingerprint")


@override_settings(FEATURE_PM_E2E_ENABLED=True)
class PrivateMessagesSecurityHardeningTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(email="alice-security@example.com", username="alice_security", password="secret123")  # type: ignore[attr-defined]
        self.bob = User.objects.create_user(email="bob-security@example.com", username="bob_security", password="secret123")  # type: ignore[attr-defined]
        self.charlie = User.objects.create_user(email="charlie-security@example.com", username="charlie_security", password="secret123")  # type: ignore[attr-defined]
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()
        self.charlie.mark_email_verified()

    def _create_key(self, actor, key_id: str, **extra):
        defaults = {
            "public_key": f"{key_id}-public",
            "fingerprint_hex": ("a" if "alice" in key_id else "b") * 64,
            "algorithm": UserIdentityKey.Algorithm.CURVE25519,
            "is_active": True,
        }
        defaults.update(extra)
        return UserIdentityKey.objects.create(actor=actor, key_id=key_id, **defaults)

    def test_send_direct_message_rejects_compromised_conversation(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self._create_key(self.alice.actor, "alice-secure-key")
        self._create_key(self.bob.actor, "bob-secure-key")
        conversation.compromised_at = timezone.now()
        conversation.compromise_reason = "simulated incident"
        conversation.save(update_fields=["compromised_at", "compromise_reason", "updated_at"])

        with self.assertRaises(ValidationError):
            send_direct_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor,
                ciphertext="ciphertext",
                message_nonce="nonce",
                client_message_id="client-compromised",
            )

    def test_send_direct_message_rejects_revoked_sender_key(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self._create_key(self.alice.actor, "alice-revoked-key", revoked_at=timezone.now())
        self._create_key(self.bob.actor, "bob-valid-key")

        with self.assertRaises(ValidationError):
            send_direct_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor,
                ciphertext="ciphertext",
                message_nonce="nonce",
                client_message_id="client-revoked",
            )

    def test_send_direct_message_rejects_expired_recipient_key(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self._create_key(self.alice.actor, "alice-valid-key")
        self._create_key(self.bob.actor, "bob-expired-key", expires_at=timezone.now() - timedelta(minutes=1))

        with self.assertRaises(ValidationError):
            send_direct_encrypted_message(
                conversation=conversation,
                sender=self.alice.actor,
                ciphertext="ciphertext",
                message_nonce="nonce",
                client_message_id="client-expired",
            )

    @override_settings(PM_CONVERSATION_CREATION_LIMIT=1, PM_CONVERSATION_CREATION_WINDOW_SECONDS=86400)
    def test_conversation_creation_limit_uses_settings(self):
        _, created = get_or_create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        self.assertTrue(created)

        with self.assertRaises(ValidationError):
            get_or_create_direct_conversation(
                created_by=self.alice.actor,
                participant_a=self.alice.actor,
                participant_b=self.charlie.actor,
            )

    @override_settings(PM_KEY_REGISTRATION_LIMIT=1, PM_KEY_REGISTRATION_WINDOW_SECONDS=86400)
    def test_key_registration_limit_uses_settings(self):
        UserIdentityKey.objects.create(
            actor=self.alice.actor,
            key_id="alice-existing-key",
            public_key="seed-public-key",
            fingerprint_hex="f" * 64,
        )
        self.client.force_login(self.alice)

        response = self.client.post(
            "/messages/keys/register/",
            {
                "key_id": "web-ecdh-limit-test",
                "public_key": "MDEyMzQ1Njc4OQ==",
                "fingerprint_hex": "a" * 64,
            },
        )
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["ok"])
