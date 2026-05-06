from __future__ import annotations

import secrets

from django.conf import settings
from django.http import HttpRequest


def is_ready_endpoint_authorized(request: HttpRequest) -> bool:
    if bool(getattr(settings, "HEALTH_READY_PUBLIC", True)):
        return True

    if bool(getattr(settings, "HEALTH_READY_ALLOW_STAFF", True)):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and (user.is_staff or user.is_superuser):
            return True

    required_token = str(getattr(settings, "HEALTH_READY_TOKEN", "") or "").strip()
    if required_token:
        presented_token = (request.headers.get("X-Health-Token") or "").strip()
        if presented_token and secrets.compare_digest(presented_token, required_token):
            return True

    allowed_ips = {ip.strip() for ip in getattr(settings, "HEALTH_READY_ALLOWED_IPS", []) if ip.strip()}
    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    if remote_addr and remote_addr in allowed_ips:
        return True

    return False
