from django.core.management.base import BaseCommand

from apps.core.models import AsyncTaskFailure


class Command(BaseCommand):
    help = "List captured async task failures (optionally only terminal failures)."

    def add_arguments(self, parser):
        parser.add_argument("--task", type=str, default="", help="Filter by task name substring")
        parser.add_argument("--terminal-only", action="store_true", help="Show only terminal failures")
        parser.add_argument("--limit", type=int, default=25, help="Maximum rows to print")

    def handle(self, *args, **options):
        task_q = options["task"].strip()
        terminal_only = options["terminal_only"]
        limit = max(1, int(options["limit"]))

        qs = AsyncTaskFailure.objects.all().order_by("-created_at")
        if terminal_only:
            qs = qs.filter(is_terminal=True)
        if task_q:
            qs = qs.filter(task_name__icontains=task_q)

        rows = list(qs[:limit])
        if not rows:
            self.stdout.write(self.style.SUCCESS("No async task failures found."))
            return

        self.stdout.write(self.style.WARNING(f"Showing {len(rows)} async task failure(s):"))
        for item in rows:
            self.stdout.write(
                " | ".join(
                    [
                        f"ts={item.created_at.isoformat()}",
                        f"task={item.task_name}",
                        f"attempt={item.attempt}/{item.max_retries}",
                        f"terminal={item.is_terminal}",
                        f"corr={item.correlation_id or '-'}",
                        f"idemp={item.idempotency_key or '-'}",
                        f"error={item.error_message[:200]}",
                    ]
                )
            )
