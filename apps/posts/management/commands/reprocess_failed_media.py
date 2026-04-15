from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.posts.models import Attachment
from apps.posts.tasks import process_media_attachment


class Command(BaseCommand):
    help = "Re-queue failed media attachments for processing."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Maximum attachments to enqueue")

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        suffix = timezone.now().strftime("manual-%Y%m%d%H%M%S")

        qs = Attachment.objects.filter(processing_state=Attachment.ProcessingState.FAILED).order_by("created_at")[:limit]
        queued = 0
        for attachment in qs:
            attachment.processing_state = Attachment.ProcessingState.PENDING
            attachment.save(update_fields=["processing_state", "updated_at"])
            process_media_attachment.delay(str(attachment.id), idempotency_suffix=suffix)
            queued += 1

        self.stdout.write(self.style.SUCCESS(f"Queued {queued} failed media attachment(s)."))
