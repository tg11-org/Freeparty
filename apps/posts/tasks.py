from __future__ import annotations

import re
from urllib.parse import quote, urlparse

import bleach
from celery import shared_task
from django.conf import settings

from apps.core.network import UnsafeRemoteURL, safe_urlopen, validate_remote_url
from apps.core.services.task_observability import observe_celery_task
from apps.core.services.task_reliability import (
    mark_task_execution_failed,
    mark_task_execution_succeeded,
    start_task_execution,
)
from apps.posts.models import Attachment


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_media_attachment(
    self,
    attachment_id: str,
    correlation_id: str | None = None,
    idempotency_suffix: str = "default",
) -> None:
    """Process media attachment asynchronously with reliability tracking.

    This is an intentionally narrow first slice for Phase 4.3 that validates media
    metadata and transitions processing state to `processed` or `failed`.
    """

    idempotency_key = f"media_processing:{attachment_id}:{idempotency_suffix}"
    execution, should_skip = start_task_execution(
        task_name=self.name,
        idempotency_key=idempotency_key,
        task_id=getattr(self.request, "id", ""),
        correlation_id=correlation_id,
        payload={"attachment_id": attachment_id},
    )
    if should_skip:
        return

    with observe_celery_task(self, correlation_id=correlation_id):
        try:
            attachment = Attachment.objects.get(id=attachment_id)
            if attachment.processing_state == Attachment.ProcessingState.PROCESSED:
                mark_task_execution_succeeded(execution)
                return

            if attachment.attachment_type not in {
                Attachment.AttachmentType.IMAGE,
                Attachment.AttachmentType.VIDEO,
            }:
                raise ValueError("Unsupported attachment type for media processing")

            if attachment.attachment_type == Attachment.AttachmentType.IMAGE and not attachment.mime_type.startswith("image/"):
                raise ValueError("Attachment metadata mismatch: expected image/* mime type")

            if attachment.attachment_type == Attachment.AttachmentType.VIDEO and not attachment.mime_type.startswith("video/"):
                raise ValueError("Attachment metadata mismatch: expected video/* mime type")

            attachment.processing_state = Attachment.ProcessingState.PROCESSED
            attachment.save(update_fields=["processing_state", "updated_at"])
            mark_task_execution_succeeded(execution)
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            Attachment.objects.filter(id=attachment_id).update(processing_state=Attachment.ProcessingState.FAILED)
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={"attachment_id": attachment_id},
                attempt=retries + 1,
                max_retries=max_retries,
            )
            raise


# ── Link unfurl helpers ────────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://[^\s"\'<>]{10,}', re.IGNORECASE)
_OEMBED_PROVIDERS = {
    # Video
    "youtube.com": "https://www.youtube.com/oembed",
    "youtu.be": "https://www.youtube.com/oembed",
    "vimeo.com": "https://vimeo.com/api/oembed.json",
    "dailymotion.com": "https://www.dailymotion.com/services/oembed",
    "twitch.tv": "https://api.twitch.tv/v5/oembed",
    "tiktok.com": "https://www.tiktok.com/oembed",
    # Audio
    "soundcloud.com": "https://soundcloud.com/oembed",
    "mixcloud.com": "https://www.mixcloud.com/oembed/",
    "bandcamp.com": "https://bandcamp.com/oembed",
    "spotify.com": "https://open.spotify.com/oembed",
    # Social / microblog
    "twitter.com": "https://publish.twitter.com/oembed",
    "x.com": "https://publish.twitter.com/oembed",
    "tumblr.com": "https://www.tumblr.com/oembed/1.0",
    # Photos / design
    "flickr.com": "https://www.flickr.com/services/oembed/",
    "flic.kr": "https://www.flickr.com/services/oembed/",
    "dribbble.com": "https://dribbble.com/services/oembed",
    "giphy.com": "https://giphy.com/services/oembed",
    # Code / dev
    "codepen.io": "https://codepen.io/api/oembed",
    "github.com": "https://github.com/api/oembed",
    # Presentations / docs
    "speakerdeck.com": "https://speakerdeck.com/oembed.json",
    "slideshare.net": "https://www.slideshare.net/api/oembed/2",
    # Crowdfunding
    "kickstarter.com": "https://www.kickstarter.com/services/oembed",
}
_OEMBED_ALLOWED_ATTRS = {
    "iframe": [
        "allow",
        "allowfullscreen",
        "height",
        "loading",
        "referrerpolicy",
        "src",
        "title",
        "width",
    ],
}


def _is_ssrf_target(url: str) -> bool:
    """Return True if the URL resolves to a private/reserved address."""
    try:
        validate_remote_url(url)
    except UnsafeRemoteURL:
        return True
    return False


def _sanitize_oembed_html(html: str) -> str:
    """Keep only allowlisted iframe markup from provider oEmbed responses."""
    cleaned = bleach.clean(
        html or "",
        tags=["iframe"],
        attributes=_OEMBED_ALLOWED_ATTRS,
        protocols=["https"],
        strip=True,
        strip_comments=True,
    ).strip()
    lowered = cleaned.lower()
    if "<iframe" not in lowered:
        return ""
    if "src=" not in lowered:
        return ""
    if any(blocked in lowered for blocked in ("javascript:", "data:", "srcdoc")):
        return ""
    return cleaned[:5000]

def _fetch_unfurl(url: str) -> dict:
    """Fetch OG/oEmbed metadata for *url*. Returns a dict of fields."""
    import urllib.request

    if _is_ssrf_target(url):
        return {"fetch_error": "SSRF blocked"}

    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")

    headers = {
        "User-Agent": "Freepartybot/1.0 (+https://freeparty.local; link preview)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
    }

    # ── oEmbed path for known video providers ───────────────────────────────
    for provider_host, oembed_endpoint in _OEMBED_PROVIDERS.items():
        if host.endswith(provider_host):
            try:
                import json
                oembed_url = f"{oembed_endpoint}?url={quote(url, safe='')}&format=json&maxwidth=680"
                req = urllib.request.Request(oembed_url, headers=headers)
                with safe_urlopen(req, timeout=8, allow_http=False, allow_redirects=False) as resp:
                    data = json.loads(resp.read(256 * 1024))
                result: dict = {
                    "url": url,
                    "title": data.get("title", "")[:500],
                    "site_name": data.get("provider_name", "")[:200],
                    "description": "",
                    "thumbnail_url": data.get("thumbnail_url", "")[:2000],
                    "embed_html": "",
                }
                # Only embed iframe for YouTube/Vimeo — sanitise to avoid XSS
                if data.get("type") in ("video", "rich") and data.get("html"):
                    result["embed_html"] = _sanitize_oembed_html(data["html"])
                return result
            except Exception as exc:  # noqa: BLE001
                return {"fetch_error": f"oEmbed error: {exc}"[:500]}

    # ── Generic OG scrape ───────────────────────────────────────────────────
    try:
        req = urllib.request.Request(url, headers=headers)
        with safe_urlopen(req, timeout=8, allow_redirects=False) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return {"fetch_error": "Non-HTML content-type"}
            html = resp.read(128 * 1024).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return {"fetch_error": f"HTTP error: {exc}"[:500]}

    def _meta(prop: str) -> str:
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']og:{prop}["\'][^>]+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE
        ) or re.search(
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']og:{prop}["\']',
            html, re.IGNORECASE
        )
        return m.group(1).strip() if m else ""

    title = _meta("title") or re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if hasattr(title, "group"):
        title = title.group(1).strip()
    title = (title or "")[:500]

    return {
        "url": url,
        "title": title,
        "description": _meta("description")[:2000],
        "thumbnail_url": _meta("image")[:2000],
        "site_name": _meta("site_name")[:200],
        "embed_html": "",
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def unfurl_post_link(self, post_id: str, correlation_id: str | None = None) -> None:
    """Fetch link preview metadata for the first URL in a post."""
    if not getattr(settings, "FEATURE_LINK_UNFURL_ENABLED", False):
        return

    idempotency_key = f"link_unfurl:{post_id}"
    execution, should_skip = start_task_execution(
        task_name=self.name,
        idempotency_key=idempotency_key,
        task_id=getattr(self.request, "id", ""),
        correlation_id=correlation_id,
        payload={
            "post_id": post_id,
            "correlation_id": correlation_id or "",
            "args": [post_id],
            "kwargs": {"correlation_id": correlation_id} if correlation_id else {},
        },
    )
    if should_skip:
        return

    with observe_celery_task(self, correlation_id=correlation_id):
        from apps.posts.models import LinkPreview, Post

        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            mark_task_execution_succeeded(execution)
            return

        # Skip if preview already fetched
        if LinkPreview.objects.filter(post_id=post_id).exists():
            mark_task_execution_succeeded(execution)
            return

        match = _URL_RE.search(post.content or "")
        if not match:
            mark_task_execution_succeeded(execution)
            return

        try:
            url = match.group(0).rstrip(".,;:!?)")
            data = _fetch_unfurl(url)

            LinkPreview.objects.update_or_create(
                post_id=post_id,
                defaults={
                    "url": url,
                    "title": data.get("title", ""),
                    "description": data.get("description", ""),
                    "thumbnail_url": data.get("thumbnail_url", ""),
                    "site_name": data.get("site_name", ""),
                    "embed_html": data.get("embed_html", ""),
                    "fetch_error": data.get("fetch_error", ""),
                },
            )
            mark_task_execution_succeeded(execution)
        except Exception as exc:
            retries = int(getattr(self.request, "retries", 0))
            max_retries = int(getattr(self, "max_retries", 0))
            mark_task_execution_failed(
                execution=execution,
                error=exc,
                is_terminal=retries >= max_retries,
                terminal_reason="max_retries_exceeded" if retries >= max_retries else "",
                task_name=self.name,
                task_id=getattr(self.request, "id", ""),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload={
                    "post_id": post_id,
                    "correlation_id": correlation_id or "",
                    "args": [post_id],
                    "kwargs": {"correlation_id": correlation_id} if correlation_id else {},
                },
                attempt=retries + 1,
                max_retries=max_retries,
            )
            raise
