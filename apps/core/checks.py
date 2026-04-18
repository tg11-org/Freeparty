from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Tags, register


def _is_production_context() -> bool:
    module_name = os.environ.get("DJANGO_SETTINGS_MODULE", "").lower()
    return module_name.endswith("production") or ".production" in module_name


@register(Tags.security, deploy=True)
def production_configuration_guardrails(app_configs, **kwargs):  # noqa: ARG001
    """Fail fast for unsafe production configuration defaults."""
    if not _is_production_context():
        return []

    errors: list[Error] = []

    if settings.DEBUG:
        errors.append(
            Error(
                "DEBUG must be False in production.",
                hint="Set DEBUG=False in production environment configuration.",
                id="core.E001",
            )
        )

    secret_key = (getattr(settings, "SECRET_KEY", "") or "").strip()
    weak_secret_values = {"", "change-me", "changeme", "secret", "insecure", "dev", "development"}
    if len(secret_key) < 32 or secret_key.lower() in weak_secret_values:
        errors.append(
            Error(
                "SECRET_KEY is weak or unset for production.",
                hint="Use a long, random SECRET_KEY (at least 32 characters).",
                id="core.E002",
            )
        )

    allowed_hosts = [host.strip().lower() for host in getattr(settings, "ALLOWED_HOSTS", []) if host.strip()]
    localhost_only = {"localhost", "127.0.0.1", "[::1]"}
    if not allowed_hosts or set(allowed_hosts).issubset(localhost_only):
        errors.append(
            Error(
                "ALLOWED_HOSTS must include at least one non-local host in production.",
                hint="Set ALLOWED_HOSTS to your public domain(s), for example freeparty.tld.",
                id="core.E003",
            )
        )

    csrf_trusted_origins = [
        origin.strip() for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) if origin.strip()
    ]
    if not csrf_trusted_origins:
        errors.append(
            Error(
                "CSRF_TRUSTED_ORIGINS is empty in production.",
                hint="Set CSRF_TRUSTED_ORIGINS to trusted https:// origins for your site.",
                id="core.E004",
            )
        )

    insecure_csrf_origins = [origin for origin in csrf_trusted_origins if not origin.lower().startswith("https://")]
    if insecure_csrf_origins and not settings.DEBUG:
        errors.append(
            Error(
                "CSRF_TRUSTED_ORIGINS contains non-HTTPS origins in production.",
                hint="Remove non-HTTPS origins from CSRF_TRUSTED_ORIGINS.",
                id="core.E005",
            )
        )

    site_domain = (getattr(settings, "SITE_DOMAIN", "") or "").strip().lower()
    if not site_domain or site_domain in localhost_only:
        errors.append(
            Error(
                "SITE_DOMAIN is not configured for production.",
                hint="Set SITE_DOMAIN to your public host, for example freeparty.tld.",
                id="core.E006",
            )
        )

    return errors