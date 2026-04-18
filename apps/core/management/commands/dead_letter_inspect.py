"""Inspect and manage terminal async task failures."""

from celery import current_app
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

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
        parser.add_argument(
            "--operator",
            type=str,
            help="Operator identifier for audit attribution (required for replay)",
        )
        parser.add_argument(
            "--note",
            type=str,
            default="",
            help="Optional audit note for replay/dismiss actions",
        )

    def handle(self, *args, **options):
        if options.get("dismiss"):
            return self._dismiss_failure(options["dismiss"], operator=options.get("operator"), note=options.get("note", ""))
        elif options.get("replay"):
            return self._replay_failure(options["replay"], operator=options.get("operator"), note=options.get("note", ""))
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

    def _dismiss_failure(self, failure_id, operator=None, note=""):
        """Mark failure as manually dismissed."""
        try:
            failure = AsyncTaskFailure.objects.get(pk=failure_id)
            payload = dict(failure.payload or {})
            payload["manual_dismissed_at"] = timezone.now().isoformat()
            if operator:
                payload["manual_dismissed_by"] = operator
            if note:
                payload["manual_dismiss_note"] = note
            failure.is_terminal = True
            failure.terminal_reason = "manual_dismiss"
            failure.payload = payload
            failure.save(update_fields=["is_terminal", "terminal_reason", "payload", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"✓ Failure {failure_id} dismissed."))
        except AsyncTaskFailure.DoesNotExist:
            raise CommandError(f"Failure {failure_id} not found.")

    def _replay_failure(self, failure_id, operator=None, note=""):
        """Replay a terminal failure back onto the task queue."""
        if not operator:
            raise CommandError("Replay requires --operator for audit attribution.")
        try:
            failure = AsyncTaskFailure.objects.get(pk=failure_id)
            registry = getattr(current_app, "tasks", {})
            task = registry.get(failure.task_name) if hasattr(registry, "get") else None
            if task is None:
                raise CommandError(f"Task {failure.task_name} is not registered in Celery.")

            replay_count = int(failure.payload.get("replay_count", 0)) if isinstance(failure.payload, dict) else 0
            max_replay_count = int(getattr(settings, "DEAD_LETTER_REPLAY_MAX_COUNT", 5))
            if replay_count >= max_replay_count:
                raise CommandError("Replay limit reached for this failure.")

            replay_cooldown_seconds = int(getattr(settings, "DEAD_LETTER_REPLAY_COOLDOWN_SECONDS", 300))
            payload = dict(failure.payload or {})
            last_replay_at = payload.get("last_replay_at")
            if last_replay_at:
                try:
                    elapsed = timezone.now() - timezone.datetime.fromisoformat(last_replay_at)
                    if elapsed.total_seconds() < replay_cooldown_seconds:
                        raise CommandError("Replay cooldown active for this failure.")
                except ValueError:
                    pass

            payload["replay_count"] = replay_count + 1
            payload["last_replay_at"] = timezone.now().isoformat()
            payload["last_replayed_by"] = operator
            if note:
                payload["last_replay_note"] = note

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
            failure.save(update_fields=["payload", "is_terminal", "terminal_reason", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"✓ Failure {failure_id} marked for replay."))
        except AsyncTaskFailure.DoesNotExist:
            raise CommandError(f"Failure {failure_id} not found.")
