from __future__ import annotations

import traceback as traceback_module

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import AsyncTaskExecution, AsyncTaskFailure


def start_task_execution(
    *,
    task_name: str,
    idempotency_key: str,
    task_id: str | None = None,
    correlation_id: str | None = None,
    payload: dict | None = None,
) -> tuple[AsyncTaskExecution, bool]:
    """Start or resume an idempotent task execution. Returns (execution, should_skip)."""
    payload = payload or {}
    task_id = task_id or ""
    correlation_id = correlation_id or ""

    try:
        with transaction.atomic():
            execution = AsyncTaskExecution.objects.create(
                task_name=task_name,
                idempotency_key=idempotency_key,
                task_id=task_id,
                correlation_id=correlation_id,
                status=AsyncTaskExecution.Status.STARTED,
                attempt_count=1,
                payload=payload,
            )
            return execution, False
    except IntegrityError:
        execution = AsyncTaskExecution.objects.get(task_name=task_name, idempotency_key=idempotency_key)
        if execution.status == AsyncTaskExecution.Status.SUCCEEDED:
            return execution, True
        execution.attempt_count += 1
        execution.task_id = task_id
        execution.correlation_id = correlation_id
        execution.status = AsyncTaskExecution.Status.STARTED
        execution.payload = payload
        execution.save(update_fields=["attempt_count", "task_id", "correlation_id", "status", "payload", "updated_at"])
        return execution, False


def mark_task_execution_succeeded(execution: AsyncTaskExecution) -> None:
    execution.status = AsyncTaskExecution.Status.SUCCEEDED
    execution.last_error = ""
    execution.last_traceback = ""
    execution.completed_at = timezone.now()
    execution.save(update_fields=["status", "last_error", "last_traceback", "completed_at", "updated_at"])


def mark_task_execution_failed(
    *,
    execution: AsyncTaskExecution,
    error: Exception,
    is_terminal: bool,
    terminal_reason: str = "",
    task_name: str,
    task_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    payload: dict | None = None,
    attempt: int = 1,
    max_retries: int = 0,
) -> None:
    error_traceback = traceback_module.format_exc()

    execution.status = AsyncTaskExecution.Status.FAILED
    execution.last_error = str(error)
    execution.last_traceback = error_traceback
    execution.save(update_fields=["status", "last_error", "last_traceback", "updated_at"])

    AsyncTaskFailure.objects.create(
        task_name=task_name,
        task_id=task_id or "",
        correlation_id=correlation_id or "",
        idempotency_key=idempotency_key or "",
        attempt=attempt,
        max_retries=max_retries,
        is_terminal=is_terminal,
        terminal_reason=terminal_reason if is_terminal else "",
        error_message=str(error),
        traceback=error_traceback,
        payload=payload or {},
    )
