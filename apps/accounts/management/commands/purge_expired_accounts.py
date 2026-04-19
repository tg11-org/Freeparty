from django.core.management.base import BaseCommand

from apps.accounts.services import AccountLifecycleService


class Command(BaseCommand):
    help = "Permanently purge accounts whose deletion/deactivation retention windows expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many accounts would be purged without deleting.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        result = AccountLifecycleService.purge_expired_accounts(dry_run=dry_run)
        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}purged_total={result['purged_total']} "
                f"purged_after_deletion_window={result['purged_after_deletion_window']} "
                f"purged_after_deactivation_window={result['purged_after_deactivation_window']}"
            )
        )
