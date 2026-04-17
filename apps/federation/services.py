from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from apps.federation.models import Instance, RemoteActor, RemotePost
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


def fetch_json_document(url: str) -> tuple[dict, dict[str, str]]:
	request = urllib.request.Request(url, headers={"Accept": "application/json"})
	with urllib.request.urlopen(request, timeout=10) as response:
		payload = response.read()
		data = json.loads(payload.decode("utf-8"))
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
	data, headers = fetch_json_document(url)
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
	data, headers = fetch_json_document(url)
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