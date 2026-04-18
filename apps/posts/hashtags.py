from __future__ import annotations

import re

from apps.posts.models import Hashtag, Post, PostHashtag

_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")


def extract_hashtags(text: str) -> list[str]:
    """Extract normalized hashtag tokens from post content."""
    tags: list[str] = []
    seen: set[str] = set()
    for match in _HASHTAG_RE.finditer(text or ""):
        tag = match.group(1).lower()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def sync_post_hashtags(post: Post) -> None:
    """Synchronize indexed hashtag mappings for a post."""
    target_tags = set(extract_hashtags(post.content or ""))
    existing_tags = set(
        PostHashtag.objects.filter(post=post).values_list("hashtag__tag", flat=True)
    )

    to_remove = existing_tags - target_tags
    to_add = target_tags - existing_tags

    if to_remove:
        PostHashtag.objects.filter(post=post, hashtag__tag__in=to_remove).delete()

    for tag in to_add:
        hashtag, _ = Hashtag.objects.get_or_create(tag=tag)
        PostHashtag.objects.get_or_create(post=post, hashtag=hashtag)
