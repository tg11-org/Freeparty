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
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSP_REPORT_ONLY_ENABLED = env.bool("CSP_REPORT_ONLY_ENABLED", default=True)
CSP_REPORT_ONLY_POLICY = env(
	"CSP_REPORT_ONLY_POLICY",
	default=(
		"default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
		"img-src 'self' data: https:; object-src 'none'; script-src 'self' 'unsafe-inline'; "
		"style-src 'self' 'unsafe-inline'"
	),
)
