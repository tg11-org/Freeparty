from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_interaction_metric(
    *,
    name: str,
    success: bool,
    duration_ms: float,
    status_code: int,
    actor_id: str = "",
    target_id: str = "",
    detail: str = "",
) -> None:
    level = logging.INFO if success else logging.WARNING
    logger.log(
        level,
        "interaction_metric name=%s success=%s duration_ms=%.2f status_code=%s actor_id=%s target_id=%s detail=%s",
        name,
        success,
        duration_ms,
        status_code,
        actor_id,
        target_id,
        detail,
    )
