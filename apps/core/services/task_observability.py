from __future__ import annotations

import logging
from contextlib import contextmanager
from time import perf_counter

logger = logging.getLogger(__name__)


def _task_id(task) -> str | None:
    request = getattr(task, "request", None)
    return getattr(request, "id", None)


@contextmanager
def observe_celery_task(task, *, correlation_id: str | None = None):
    task_name = getattr(task, "name", task.__class__.__name__)
    task_id = _task_id(task)
    logger.info(
        "task_start task=%s task_id=%s correlation_id=%s",
        task_name,
        task_id,
        correlation_id,
    )
    start = perf_counter()
    try:
        yield
    except Exception:
        duration_ms = (perf_counter() - start) * 1000
        logger.exception(
            "task_failure task=%s task_id=%s duration_ms=%.2f correlation_id=%s",
            task_name,
            task_id,
            duration_ms,
            correlation_id,
        )
        raise

    duration_ms = (perf_counter() - start) * 1000
    logger.info(
        "task_success task=%s task_id=%s duration_ms=%.2f correlation_id=%s",
        task_name,
        task_id,
        duration_ms,
        correlation_id,
    )
