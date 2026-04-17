from __future__ import annotations

import base64
import hashlib
import hmac
import time


def _parse_unix_timestamp(timestamp: str) -> int | None:
	try:
		return int(timestamp)
	except (TypeError, ValueError):
		return None


def sign_payload(*, payload: bytes, shared_secret: str, timestamp: str | None = None) -> dict[str, str]:
	resolved_timestamp = timestamp or str(int(time.time()))
	message = resolved_timestamp.encode("utf-8") + b"." + payload
	digest = hmac.new(shared_secret.encode("utf-8"), message, hashlib.sha256).digest()
	return {
		"timestamp": resolved_timestamp,
		"signature": base64.b64encode(digest).decode("ascii"),
	}


def build_signed_headers(*, payload: bytes, key_id: str, shared_secret: str, timestamp: str | None = None) -> dict[str, str]:
	if not shared_secret:
		raise ValueError("Federation shared secret is required for signed delivery.")
	signed = sign_payload(payload=payload, shared_secret=shared_secret, timestamp=timestamp)
	return {
		"X-Freeparty-Key-Id": key_id,
		"X-Freeparty-Timestamp": signed["timestamp"],
		"X-Freeparty-Signature": signed["signature"],
	}


def verify_signed_payload(
	*,
	payload: bytes,
	shared_secret: str,
	timestamp: str,
	signature: str,
	max_age_seconds: int = 300,
	now_ts: int | None = None,
) -> bool:
	if max_age_seconds < 1:
		return False
	parsed_timestamp = _parse_unix_timestamp(timestamp)
	if parsed_timestamp is None:
		return False
	current_timestamp = now_ts if now_ts is not None else int(time.time())
	if abs(current_timestamp - parsed_timestamp) > max_age_seconds:
		return False
	expected = sign_payload(payload=payload, shared_secret=shared_secret, timestamp=timestamp)
	return hmac.compare_digest(expected["signature"], signature)