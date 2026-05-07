import json

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.federation.models import FederationObject, Instance
from apps.federation.services import ingest_inbound_activity, normalize_instance_domain, validate_inbound_signature


def _instance_domain_from_key_id(key_id: str) -> str:
	value = str(key_id or "").strip()
	if value.startswith("freeparty:"):
		value = value.split(":", 1)[1]
	return normalize_instance_domain(value)


@csrf_exempt
@require_POST
def inbox(request: HttpRequest) -> JsonResponse:
	if not getattr(settings, "FEATURE_FEDERATION_INBOUND_ENABLED", False):
		return JsonResponse({"detail": "Federation inbound is disabled."}, status=503)

	signature = request.headers.get("X-Freeparty-Signature", "")
	timestamp = request.headers.get("X-Freeparty-Timestamp", "")
	key_id = request.headers.get("X-Freeparty-Key-Id", "")
	domain = _instance_domain_from_key_id(key_id)
	if not domain:
		return JsonResponse({"detail": "Missing federation key id."}, status=400)

	instance = Instance._default_manager.filter(domain=domain).first()
	if instance is None:
		return JsonResponse({"detail": "Unknown federation instance."}, status=403)
	if instance.allowlist_state != Instance.AllowlistState.ALLOWED or instance.is_blocked:
		return JsonResponse({"detail": "Federation instance is not allowlisted."}, status=403)

	raw_payload = request.body or b""
	if not raw_payload:
		return JsonResponse({"detail": "Request body is required."}, status=400)

	if not validate_inbound_signature(
		instance=instance,
		raw_payload=raw_payload,
		timestamp=timestamp,
		signature=signature,
		key_id=key_id,
	):
		return JsonResponse({"detail": "Invalid federation signature."}, status=403)

	try:
		payload = json.loads(raw_payload.decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError):
		return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

	try:
		federation_object = ingest_inbound_activity(
			instance=instance,
			payload=payload,
			signature_metadata={"signature": signature, "timestamp": timestamp, "key_id": key_id},
		)
	except ValueError as exc:
		fallback_uri = str(payload.get("id") or "").strip() or f"urn:freeparty:failed:{domain}:{timestamp}"
		FederationObject.objects.update_or_create(
			external_id=fallback_uri,
			defaults={
				"instance": instance,
				"canonical_uri": fallback_uri,
				"object_type": FederationObject.ObjectType.OTHER,
				"payload": payload,
				"signature_metadata": {"signature": signature, "timestamp": timestamp, "key_id": key_id},
				"processing_state": FederationObject.ProcessingState.FAILED,
			},
		)
		return JsonResponse({"detail": str(exc)}, status=400)

	return JsonResponse(
		{
			"status": "accepted",
			"object_id": str(federation_object.id),
			"processing_state": federation_object.processing_state,
		},
		status=202,
	)
