"""Inspect and manage terminal async task failures."""

from celery import current_app
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import AsyncTaskFailure


class Command(BaseCommand):
    help = "Inspect dead-letter queue and manage terminal async task failures (Phase 7.2)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Limit results (default: 25)",
        )
        parser.add_argument(
            "--terminal-only",
            action="store_true",
            help="Show only terminal failures",
        )
        parser.add_argument(
            "--task",
            type=str,
            help="Filter by task name",
        )
        parser.add_argument(
            "--reason",
            type=str,
            help="Filter by terminal reason",
        )
        parser.add_argument(
            "--dismiss",
            type=str,
            help="Mark failure as manually dismissed (provide ID)",
        )
        parser.add_argument(
            "--replay",
            type=str,
            help="Mark failure for replay (provide ID)",
        )

    def handle(self, *args, **options):
        if options.get("dismiss"):
            return self._dismiss_failure(options["dismiss"])
        elif options.get("replay"):
            return self._replay_failure(options["replay"])
        else:
            return self._inspect_queue(options)

    def _inspect_queue(self, options):
        """Display dead-letter queue."""
        qs = AsyncTaskFailure.objects.all().order_by("-created_at")

        if options["terminal_only"]:
            qs = qs.filter(is_terminal=True)

        if options["task"]:
            qs = qs.filter(task_name__icontains=options["task"])

        if options["reason"]:
            qs = qs.filter(terminal_reason=options["reason"])

        qs = qs[: options["limit"]]

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No failures matching query."))
            return

        self.stdout.write(self.style.SUCCESS(f"Dead-Letter Queue ({qs.count()} results):"))
        self.stdout.write("=" * 120)

        for failure in qs:
            status = ""
            if failure.is_terminal:
                status = f" [TERMINAL: {failure.terminal_reason}]"
            else:
                status = f" [Attempt {failure.attempt}/{failure.max_retries}]"

            self.stdout.write(f"\n[{failure.id}]{status}")
            self.stdout.write(f"  Task: {failure.task_name}")
            self.stdout.write(f"  Created: {failure.created_at}")
            self.stdout.write(f"  Error: {failure.error_message[:100]}...")

            if failure.correlation_id:
                self.stdout.write(f"  Correlation ID: {failure.correlation_id}")

            self.stdout.write(
                self.style.WARNING(
                    f"  Actions: dismiss --dismiss {failure.id} | replay --replay {failure.id}"
                )
            )

    def _dismiss_failure(self, failure_id):
        """Mark failure as manually dismissed."""
        try:
            failure = AsyncTaskFailure.objects.get(pk=failure_id)
            failure.is_terminal = True
            failure.terminal_reason = "manual_dismiss"
            failure.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Failure {failure_id} dismissed."))
        except AsyncTaskFailure.DoesNotExist:
            raise CommandError(f"Failure {failure_id} not found.")

    def _replay_failure(self, failure_id):
        """Replay a terminal failure back onto the task queue."""
        try:
            failure = AsyncTaskFailure.objects.get(pk=failure_id)
            registry = getattr(current_app, "tasks", {})
            task = registry.get(failure.task_name) if hasattr(registry, "get") else None
            if task is None:
                raise CommandError(f"Task {failure.task_name} is not registered in Celery.")

            replay_count = int(failure.payload.get("replay_count", 0)) if isinstance(failure.payload, dict) else 0
            if replay_count >= 5:
                raise CommandError("Replay limit reached for this failure.")

            payload = dict(failure.payload or {})
            payload["replay_count"] = replay_count + 1

            apply_kwargs = {}
            if isinstance(payload, dict):
                payload_args = payload.get("args")
                payload_kwargs = payload.get("kwargs")
                if isinstance(payload_args, list):
                    apply_kwargs["args"] = payload_args
                if isinstance(payload_kwargs, dict):
                    apply_kwargs["kwargs"] = payload_kwargs

            if not apply_kwargs:
                inferred_args = []
                if "delivery_id" in payload:
                    inferred_args = [payload["delivery_id"]]
                elif "notification_id" in payload:
                    inferred_args = [payload["notification_id"]]
                elif "attachment_id" in payload:
                    inferred_args = [payload["attachment_id"]]
                elif "post_id" in payload:
                    inferred_args = [payload["post_id"]]
                elif "recipient_email" in payload:
                    inferred_args = []
                apply_kwargs["args"] = inferred_args
                correlation_id = payload.get("correlation_id") or failure.correlation_id
                if correlation_id:
                    apply_kwargs["kwargs"] = {"correlation_id": correlation_id}

            task.apply_async(**apply_kwargs)

            failure.payload = payload
            failure.is_terminal = True
            failure.terminal_reason = "manual_replay"
            failure.save()
            self.stdout.write(self.style.SUCCESS(f"✓ Failure {failure_id} marked for replay."))
        except AsyncTaskFailure.DoesNotExist:
            raise CommandError(f"Failure {failure_id} not found.")
