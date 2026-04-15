from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageEnvelope, UserIdentityKey
from apps.private_messages.security import (
    canonical_safety_fingerprint_input,
    has_remote_key_changed,
    compute_identicon_seed,
    compute_safety_fingerprint_hex,
)
from apps.private_messages.services import create_direct_conversation, store_encrypted_message


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
        self.assertEqual(payload["envelopes"][0]["id"], str(second.id))
        self.assertIn("alice-key-1", payload["public_keys_by_key_id"])
        self.assertIn("bob-key-1", payload["public_keys_by_key_id"])

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
