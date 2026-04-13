from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class RequestObservabilityMiddleware:
    """Adds request correlation, completion logs, and slow/error observability."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-ID", "").strip() or uuid4().hex
        request.request_id = request_id
        user_id = request.user.id if getattr(request, "user", None) and request.user.is_authenticated else None

        start = perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = (perf_counter() - start) * 1000
            logger.exception(
                "request_error method=%s path=%s duration_ms=%.2f request_id=%s user_id=%s",
                request.method,
                request.path,
                duration_ms,
                request_id,
                user_id,
            )
            raise

        duration_ms = (perf_counter() - start) * 1000

        response["X-Request-ID"] = request_id

        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f request_id=%s user_id=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
            user_id,
        )

        slow_threshold_ms = int(getattr(settings, "REQUEST_SLOW_MS", 700))
        if duration_ms >= slow_threshold_ms:
            logger.warning(
                "slow_request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                request_id,
            )

        return response
