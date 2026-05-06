import json
import time
from unittest.mock import patch

import httpx
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.core.models import AsyncTaskExecution
from apps.federation.models import FederationDelivery, Instance, RemoteActor, RemotePost
from apps.federation.services import fetch_remote_actor, fetch_remote_object
from apps.federation.signing import sign_payload
from apps.federation.tasks import execute_federation_delivery


def _httpx_response(url: str, payload: dict, *, method: str = "GET", status: int = 202, headers: dict | None = None) -> httpx.Response:
	return httpx.Response(
		status,
		json=payload,
		headers=headers or {},
		request=httpx.Request(method, url),
	)


@override_settings(FEATURE_FEDERATION_OUTBOUND_ENABLED=True, FEDERATION_SHARED_SECRET="shared-secret")
class FederationTaskReliabilityTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="federation-owner@example.com", username="federationowner", password="secret123")
		self.user.mark_email_verified()
		self.instance = Instance._default_manager.create(
			domain="remote.example",
			allowlist_state=Instance.AllowlistState.ALLOWED,
			metadata={"shared_secret": "shared-secret", "inbox_url": "https://remote.example/inbox"},
		)
		self.delivery = FederationDelivery.objects.create(
			target_instance=self.instance,
			actor=self.user.actor,
			object_uri="https://example.com/objects/1",
			activity_payload={"type": "Create"},
		)

	@patch("apps.federation.tasks.safe_fetch")
	def test_execute_federation_delivery_marks_success_and_records_execution(self, mocked_fetch):
		mocked_fetch.return_value = _httpx_response("https://remote.example/inbox", {"status": "accepted"}, method="POST", status=202)
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-1")

		self.delivery.refresh_from_db()
		self.assertEqual(self.delivery.state, FederationDelivery.DeliveryState.SUCCESS)
		self.assertEqual(self.delivery.response_code, 202)

		execution = AsyncTaskExecution.objects.get(
			task_name="apps.federation.tasks.execute_federation_delivery",
			idempotency_key=f"federation_delivery:{self.delivery.id}",
		)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
		self.assertEqual(execution.attempt_count, 1)
		headers = mocked_fetch.call_args.kwargs["headers"]
		self.assertEqual(headers["X-Freeparty-Key-Id"], "freeparty:remote.example")
		self.assertIn("X-Freeparty-Signature", headers)

	@patch("apps.federation.tasks.safe_fetch")
	def test_execute_federation_delivery_is_idempotent_after_success(self, mocked_fetch):
		mocked_fetch.return_value = _httpx_response("https://remote.example/inbox", {"status": "accepted"}, method="POST", status=202)
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-2")
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-2")

		execution = AsyncTaskExecution.objects.get(
			task_name="apps.federation.tasks.execute_federation_delivery",
			idempotency_key=f"federation_delivery:{self.delivery.id}",
		)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
		self.assertEqual(execution.attempt_count, 1)
		self.assertEqual(mocked_fetch.call_count, 1)


class FederationInboundFetchTests(TestCase):
	def setUp(self):
		self.instance = Instance._default_manager.create(
			domain="remote.example",
			allowlist_state=Instance.AllowlistState.ALLOWED,
			metadata={"shared_secret": "shared-secret"},
		)

	def _signed_headers(self, payload: dict, *, key_id: str = "freeparty:remote.example", timestamp: str | None = None) -> dict[str, str]:
		encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
		signed = sign_payload(payload=encoded, shared_secret="shared-secret", timestamp=timestamp)
		return {
			"X-Freeparty-Signature": signed["signature"],
			"X-Freeparty-Timestamp": signed["timestamp"],
			"X-Freeparty-Key-Id": key_id,
		}

	@patch("apps.federation.services.safe_fetch")
	def test_fetch_remote_actor_persists_allowlisted_actor(self, mocked_fetch):
		payload = {
			"id": "https://remote.example/actors/alice",
			"preferredUsername": "alice",
			"name": "Alice Remote",
			"publicKey": {"publicKeyPem": "PUBLIC"},
		}
		mocked_fetch.return_value = _httpx_response(
			"https://remote.example/actors/alice",
			payload,
			status=200,
			headers=self._signed_headers(payload),
		)

		remote_actor = fetch_remote_actor("https://remote.example/actors/alice")

		self.assertEqual(remote_actor.handle, "alice")
		self.assertEqual(RemoteActor.objects.count(), 1)

	@patch("apps.federation.services.safe_fetch")
	def test_fetch_remote_object_persists_remote_post(self, mocked_fetch):
		actor_payload = {
			"id": "https://remote.example/actors/alice",
			"preferredUsername": "alice",
			"name": "Alice Remote",
			"publicKey": {"publicKeyPem": "PUBLIC"},
		}
		post_payload = {
			"id": "https://remote.example/objects/1",
			"type": "Note",
			"content": "hello from remote",
			"attributedTo": "https://remote.example/actors/alice",
			"attachment": [{"url": "https://remote.example/media/1.png", "mediaType": "image/png"}],
		}
		mocked_fetch.side_effect = [
			_httpx_response("https://remote.example/objects/1", post_payload, status=200, headers=self._signed_headers(post_payload)),
			_httpx_response("https://remote.example/actors/alice", actor_payload, status=200, headers=self._signed_headers(actor_payload)),
		]

		remote_post = fetch_remote_object("https://remote.example/objects/1")

		self.assertEqual(remote_post.content, "hello from remote")
		self.assertEqual(remote_post.remote_actor.handle, "alice")
		self.assertEqual(RemotePost.objects.count(), 1)

	def test_fetch_remote_actor_rejects_non_allowlisted_instance(self):
		Instance._default_manager.filter(id=self.instance.id).update(allowlist_state=Instance.AllowlistState.PENDING)

		with self.assertRaisesMessage(ValueError, "Remote instance is not allowlisted."):
			fetch_remote_actor("https://remote.example/actors/alice")

	@patch("apps.federation.services.safe_fetch")
	def test_fetch_remote_actor_rejects_stale_signature(self, mocked_fetch):
		payload = {
			"id": "https://remote.example/actors/alice",
			"preferredUsername": "alice",
			"name": "Alice Remote",
			"publicKey": {"publicKeyPem": "PUBLIC"},
		}
		stale_timestamp = str(int(time.time()) - 3600)
		mocked_fetch.return_value = _httpx_response(
			"https://remote.example/actors/alice",
			payload,
			status=200,
			headers=self._signed_headers(payload, timestamp=stale_timestamp),
		)

		with self.assertRaisesMessage(ValueError, "Invalid federation signature."):
			fetch_remote_actor("https://remote.example/actors/alice")

	@patch("apps.federation.services.safe_fetch")
	def test_fetch_remote_actor_rejects_unexpected_partner_key_id(self, mocked_fetch):
		Instance._default_manager.filter(id=self.instance.id).update(
			metadata={"shared_secret": "shared-secret", "inbound_key_id": "partner-key-1"}
		)
		payload = {
			"id": "https://remote.example/actors/alice",
			"preferredUsername": "alice",
			"name": "Alice Remote",
			"publicKey": {"publicKeyPem": "PUBLIC"},
		}
		mocked_fetch.return_value = _httpx_response(
			"https://remote.example/actors/alice",
			payload,
			status=200,
			headers=self._signed_headers(payload, key_id="different-key"),
		)

		with self.assertRaisesMessage(ValueError, "Invalid federation signature."):
			fetch_remote_actor("https://remote.example/actors/alice")

	@patch("apps.federation.services.safe_fetch")
	def test_fetch_remote_actor_rejects_redirect_to_different_host(self, mocked_fetch):
		mocked_fetch.side_effect = ValueError("Remote URL host does not match the expected domain.")

		with self.assertRaisesMessage(ValueError, "Remote URL host does not match the expected domain."):
			fetch_remote_actor("https://remote.example/actors/alice")
