from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.posts.hashtags import sync_post_hashtags
from apps.posts.models import Post


class Command(BaseCommand):
    help = "Backfill indexed hashtag mappings for existing posts."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Optional max number of posts to process.")

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 0)
        queryset = Post.objects.filter(deleted_at__isnull=True).order_by("created_at")
        if limit > 0:
            queryset = queryset[:limit]

        processed = 0
        for post in queryset.iterator():
            sync_post_hashtags(post)
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"Backfilled hashtag index for {processed} post(s)."))
