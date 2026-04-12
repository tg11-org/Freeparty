from .base import *  # noqa: F401,F403

DEBUG = True

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Email configuration for local testing with MailHog
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "mailhog"
EMAIL_PORT = 1025
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = "noreply@freeparty.local"

