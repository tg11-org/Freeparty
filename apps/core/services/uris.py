from urllib.parse import urljoin

from django.conf import settings


def actor_uri(handle: str) -> str:
    return urljoin(f"{settings.SITE_URL}/", f"actors/{handle}/")


def post_uri(post_id) -> str:
    return urljoin(f"{settings.SITE_URL}/", f"posts/{post_id}/")
