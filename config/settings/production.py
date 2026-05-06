from .base import *  # noqa: F401,F403
import environ

env = environ.Env()

DEBUG = False

# ── Mailcow SMTP (production) ─────────────────────────────────────────────────
# Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend in prod env.
# Remaining keys (EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER /
# EMAIL_HOST_PASSWORD / EMAIL_USE_TLS) are inherited from base.py env reads.
# Run `manage.py check_smtp` to verify connectivity before deploying.
# ─────────────────────────────────────────────────────────────────────────────

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Keep current behavior by default, but allow staged CSP hardening via CSP_ROLLOUT_MODE.
CSP_ROLLOUT_MODE = env("CSP_ROLLOUT_MODE", default="legacy-report-only").strip().lower()
if CSP_ROLLOUT_MODE == "legacy-report-only":
	CSP_REPORT_ONLY_ENABLED = env.bool("CSP_REPORT_ONLY_ENABLED", default=True)

# Readiness should not be publicly detailed in production by default.
HEALTH_READY_PUBLIC = env.bool("HEALTH_READY_PUBLIC", default=False)
