from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.utils import timezone

from apps.core.network import safe_fetch, safe_urlopen
from apps.federation.models import FederationDelivery, FederationObject, Instance, RemoteActor, RemotePost
from apps.federation.signing import verify_signed_payload


def normalize_instance_domain(domain_or_url: str) -> str:
	parsed = urlparse(domain_or_url if "://" in domain_or_url else f"https://{domain_or_url}")
	return (parsed.netloc or parsed.path).lower().strip()


def is_instance_allowed(instance_domain: str) -> bool:
	domain = normalize_instance_domain(instance_domain)
	instance = Instance._default_manager.filter(domain=domain).first()
	if instance is None:
		return False
	return not instance.is_blocked and instance.allowlist_state == Instance.AllowlistState.ALLOWED


def fetch_json_document(url: str, *, expected_domain: str | None = None) -> tuple[dict, dict[str, str]]:
	response = safe_fetch(
		url,
		method="GET",
		headers={"Accept": "application/json"},
		timeout=10,
		allowed_domain=expected_domain,
		allow_http=False,
	)
	response.raise_for_status()
	data = response.json()
	headers = {
		"signature": response.headers.get("X-Freeparty-Signature", ""),
		"timestamp": response.headers.get("X-Freeparty-Timestamp", ""),
		"key_id": response.headers.get("X-Freeparty-Key-Id", ""),
	}
	return data, headers


def validate_inbound_signature(*, instance: Instance, raw_payload: bytes, timestamp: str, signature: str, key_id: str) -> bool:
	shared_secret = instance.metadata.get("shared_secret", "")
	if not shared_secret:
		return False
	if not timestamp or not signature:
		return False

	expected_key_id = str(instance.metadata.get("inbound_key_id", "")).strip()
	if expected_key_id and key_id != expected_key_id:
		return False

	default_max_age_seconds = int(getattr(settings, "FEDERATION_SIGNATURE_MAX_AGE_SECONDS", 300))
	instance_max_age = instance.metadata.get("signature_max_age_seconds", default_max_age_seconds)
	try:
		max_age_seconds = int(instance_max_age)
	except (TypeError, ValueError):
		max_age_seconds = default_max_age_seconds
	if max_age_seconds < 1:
		max_age_seconds = default_max_age_seconds

	return verify_signed_payload(
		payload=raw_payload,
		shared_secret=shared_secret,
		timestamp=timestamp,
		signature=signature,
		max_age_seconds=max_age_seconds,
	)


def sanitize_actor_payload(data: dict) -> dict:
	return {
		"handle": str(data.get("preferredUsername") or data.get("handle") or "").strip(),
		"display_name": str(data.get("name") or "").strip(),
		"canonical_uri": str(data.get("id") or data.get("url") or "").strip(),
		"public_key": str((data.get("publicKey") or {}).get("publicKeyPem") or data.get("public_key") or "").strip(),
		"avatar_url": str(((data.get("icon") or {}).get("url")) or data.get("avatar_url") or "").strip(),
	}


def sanitize_post_payload(data: dict) -> dict:
	attachment_urls = []
	for item in data.get("attachment", []) or []:
		if isinstance(item, dict) and item.get("url"):
			attachment_urls.append({"url": item.get("url"), "mediaType": item.get("mediaType", "")})
	return {
		"canonical_uri": str(data.get("id") or data.get("url") or "").strip(),
		"content": str(data.get("content") or "").strip(),
		"attachments": attachment_urls,
		"metadata": {"type": data.get("type", "")},
	}


def fetch_remote_actor(url: str) -> RemoteActor:
	domain = normalize_instance_domain(url)
	if not is_instance_allowed(domain):
		raise ValueError("Remote instance is not allowlisted.")
	instance = Instance._default_manager.get(domain=domain)
	data, headers = fetch_json_document(url, expected_domain=domain)
	raw_payload = json.dumps(data, sort_keys=True).encode("utf-8")
	if not validate_inbound_signature(
		instance=instance,
		raw_payload=raw_payload,
		timestamp=headers.get("timestamp", ""),
		signature=headers.get("signature", ""),
		key_id=headers.get("key_id", ""),
	):
		raise ValueError("Invalid federation signature.")
	sanitized = sanitize_actor_payload(data)
	if not sanitized["handle"] or not sanitized["canonical_uri"]:
		raise ValueError("Remote actor payload missing required fields.")
	remote_actor, _ = RemoteActor.objects.update_or_create(
		canonical_uri=sanitized["canonical_uri"],
		defaults={**sanitized, "instance": instance, "fetched_at": timezone.now()},
	)
	return remote_actor


def fetch_remote_object(url: str) -> RemotePost:
	domain = normalize_instance_domain(url)
	if not is_instance_allowed(domain):
		raise ValueError("Remote instance is not allowlisted.")
	instance = Instance._default_manager.get(domain=domain)
	data, headers = fetch_json_document(url, expected_domain=domain)
	raw_payload = json.dumps(data, sort_keys=True).encode("utf-8")
	if not validate_inbound_signature(
		instance=instance,
		raw_payload=raw_payload,
		timestamp=headers.get("timestamp", ""),
		signature=headers.get("signature", ""),
		key_id=headers.get("key_id", ""),
	):
		raise ValueError("Invalid federation signature.")
	sanitized = sanitize_post_payload(data)
	if not sanitized["canonical_uri"]:
		raise ValueError("Remote object payload missing canonical URI.")
	actor_url = str((data.get("attributedTo") or data.get("actor") or "")).strip()
	if not actor_url:
		raise ValueError("Remote object payload missing actor reference.")
	remote_actor = fetch_remote_actor(actor_url)
	remote_post, _ = RemotePost.objects.update_or_create(
		canonical_uri=sanitized["canonical_uri"],
		defaults={**sanitized, "instance": instance, "remote_actor": remote_actor, "fetched_at": timezone.now()},
	)
	return remote_post


def build_post_create_activity(post) -> dict:
	attachments = []
	for attachment in post.attachments.all():
		attachments.append(
			{
				"url": attachment.file.url,
				"mediaType": attachment.mime_type,
				"name": attachment.caption or "",
			}
		)

	object_payload = {
		"id": post.canonical_uri,
		"type": "Note",
		"attributedTo": post.author.canonical_uri,
		"content": post.content,
		"attachment": attachments,
		"published": post.created_at.isoformat(),
	}

	return {
		"id": f"{post.canonical_uri}#create",
		"type": "Create",
		"actor": post.author.canonical_uri,
		"object": object_payload,
		"published": post.created_at.isoformat(),
	}


def enqueue_post_for_federation(post) -> int:
	if not getattr(settings, "FEATURE_FEDERATION_OUTBOUND_ENABLED", False):
		return 0
	if post.local_only or not post.federated:
		return 0
	if post.visibility not in {"public", "unlisted"}:
		return 0

	allowed_instances = Instance._default_manager.filter(
		allowlist_state=Instance.AllowlistState.ALLOWED,
		is_blocked=False,
	)
	activity_payload = build_post_create_activity(post)
	deliveries = []
	for instance in allowed_instances:
		delivery, created = FederationDelivery.objects.get_or_create(
			target_instance=instance,
			object_uri=post.canonical_uri,
			defaults={
				"actor": post.author,
				"activity_payload": activity_payload,
				"state": FederationDelivery.DeliveryState.PENDING,
			},
		)
		if created:
			deliveries.append(delivery)

	if not deliveries:
		return 0

	from apps.federation.tasks import execute_federation_delivery

	for delivery in deliveries:
		execute_federation_delivery.delay(str(delivery.id))
	return len(deliveries)


def _resolve_actor_handle(actor_uri: str) -> str:
	path = urlparse(actor_uri).path.strip("/")
	if not path:
		return "remote"
	segments = [segment for segment in path.split("/") if segment]
	return segments[-1][:255] if segments else "remote"


def ingest_inbound_activity(*, instance: Instance, payload: dict, signature_metadata: dict[str, str]) -> FederationObject:
	activity_id = str(payload.get("id") or "").strip()
	activity_type = str(payload.get("type") or "").strip().lower()
	object_data = payload.get("object") if isinstance(payload.get("object"), dict) else {}
	object_uri = str(object_data.get("id") or payload.get("object") or activity_id).strip()
	if not activity_id:
		activity_id = object_uri
	if not object_uri:
		raise ValueError("Inbound activity payload missing object identifier.")

	if activity_type == "create" and object_data:
		actor_uri = str(object_data.get("attributedTo") or payload.get("actor") or "").strip()
		if actor_uri:
			remote_actor, _ = RemoteActor.objects.update_or_create(
				canonical_uri=actor_uri,
				defaults={
					"instance": instance,
					"handle": _resolve_actor_handle(actor_uri),
					"display_name": "",
					"fetched_at": timezone.now(),
				},
			)
			RemotePost.objects.update_or_create(
				canonical_uri=object_uri,
				defaults={
					"instance": instance,
					"remote_actor": remote_actor,
					"content": str(object_data.get("content") or "").strip(),
					"attachments": object_data.get("attachment") or [],
					"metadata": {
						"type": object_data.get("type", ""),
						"inbound_activity_type": activity_type,
					},
					"fetched_at": timezone.now(),
				},
			)

	object_type = FederationObject.ObjectType.OTHER
	object_kind = str(object_data.get("type") or "").strip().lower()
	if object_kind in {"person", "actor", "service", "application"}:
		object_type = FederationObject.ObjectType.ACTOR
	elif object_kind in {"note", "article", "image", "video"}:
		object_type = FederationObject.ObjectType.POST

	federation_object, _ = FederationObject.objects.update_or_create(
		external_id=activity_id,
		defaults={
			"instance": instance,
			"canonical_uri": object_uri,
			"object_type": object_type,
			"payload": payload,
			"signature_metadata": signature_metadata,
			"fetched_at": timezone.now(),
			"processing_state": FederationObject.ProcessingState.PROCESSED,
		},
	)

	instance.last_seen_at = timezone.now()
	instance.save(update_fields=["last_seen_at", "updated_at"])
	return federation_object
