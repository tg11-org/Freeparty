from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_smtp_delivery_event(
    *,
    event: str,
    task_name: str,
    task_id: str | None,
    correlation_id: str | None,
    recipient_count: int,
    attempt: int,
    max_retries: int,
    will_retry: bool,
    error: str = "",
) -> None:
    logger.info(
        "smtp_delivery event=%s task=%s task_id=%s correlation_id=%s recipient_count=%s attempt=%s max_retries=%s will_retry=%s error=%s",
        event,
        task_name,
        task_id,
        correlation_id,
        recipient_count,
        attempt,
        max_retries,
        will_retry,
        error,
    )
