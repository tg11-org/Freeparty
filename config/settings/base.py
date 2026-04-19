from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    REQUEST_SLOW_MS=(int, 700),
    FEATURE_PM_E2E_ENABLED=(bool, False),
    FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=(bool, False),
    FEATURE_PM_WEBSOCKET_ENABLED=(bool, False),
    FEATURE_FEDERATION_OUTBOUND_ENABLED=(bool, False),
    FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED=(bool, True),
    ABUSE_VELOCITY_BLOCK_ENABLED=(bool, True),
    ABUSE_MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST=(int, 7),
    ABUSE_EMAIL_VERIFICATION_TRUST_BONUS=(int, 25),
    ABUSE_RECENT_REPORT_PENALTY_PER_REPORT=(int, 10),
    ABUSE_RECENT_ACTION_PENALTY_PER_ACTION=(int, 15),
    ABUSE_TRUST_SCORE_THROTTLE_THRESHOLD=(int, 30),
    ABUSE_THRESHOLD_POSTS_PER_HOUR=(int, 5),
    ABUSE_THRESHOLD_FOLLOWS_PER_HOUR=(int, 10),
    ABUSE_THRESHOLD_LIKES_PER_HOUR=(int, 20),
    ABUSE_THRESHOLD_REPOSTS_PER_HOUR=(int, 10),
    ABUSE_THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD=(int, 3),
    ABUSE_THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD=(int, 4),
    ABUSE_THROTTLE_RECENT_ACTIONS_DAYS=(int, 7),
    ABUSE_THROTTLE_RECENT_REPORTS_DAYS=(int, 3),
    ABUSE_THROTTLE_POSTING_VELOCITY_HOURS=(int, 1),
    ABUSE_THROTTLE_LOW_TRUST_HOURS=(int, 6),
    ABUSE_PROFILE_AVATAR_TRUST_BONUS=(int, 10),
    ABUSE_PROFILE_BIO_TRUST_BONUS=(int, 8),
    ABUSE_HAS_POSTS_TRUST_BONUS=(int, 5),
    ABUSE_HAS_LIKED_TRUST_BONUS=(int, 5),
    ABUSE_HAS_FOLLOWERS_TRUST_BONUS=(int, 10),
    ABUSE_HAS_FOLLOWING_TRUST_BONUS=(int, 5),
    DEAD_LETTER_REPLAY_MAX_COUNT=(int, 5),
    DEAD_LETTER_REPLAY_COOLDOWN_SECONDS=(int, 300),
    FEDERATION_SIGNATURE_MAX_AGE_SECONDS=(int, 300),
    CORS_ALLOWED_ORIGINS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    EMAIL_VERIFICATION_REQUIRED=(bool, True),
    LEGAL_TOS_VERSION=(str, "1.0"),
    LEGAL_GUIDELINES_VERSION=(str, "1.0"),
    ACCOUNT_DELETION_RETENTION_DAYS=(int, 30),
    ACCOUNT_DEACTIVATION_RETENTION_DAYS=(int, 365),
    ACCOUNT_PURGE_ENABLED=(bool, True),
    ACCOUNT_PURGE_CRON_HOUR=(int, 3),
    ACCOUNT_PURGE_CRON_MINUTE=(int, 15),
    MAIL_SERVER_HOST=(str, ""),
    MAIL_SERVER_IPV4=(str, ""),
    MAIL_SERVER_IPV6=(str, ""),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

SITE_SCHEME = env("SITE_SCHEME", default="http")
SITE_DOMAIN = env("SITE_DOMAIN", default="localhost:8000")
SITE_URL = f"{SITE_SCHEME}://{SITE_DOMAIN}"

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "rest_framework",
    "channels",
    "corsheaders",
    "apps.accounts",
    "apps.actors",
    "apps.core",
    "apps.federation",
    "apps.moderation",
    "apps.notifications",
    "apps.private_messages",
    "apps.posts",
    "apps.profiles",
    "apps.social",
    "apps.timelines",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.RequestObservabilityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.inbox_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://freeparty:freeparty@localhost:5432/freeparty",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"
LOGIN_URL = "accounts:login"

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@freeparty.local")

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
TESTING = "test" in sys.argv

if TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "freeparty-tests",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }

RATELIMIT_USE_CACHE = "default"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": env.int("API_PAGE_SIZE", default=20),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("API_THROTTLE_USER", default="120/min"),
        "anon": env("API_THROTTLE_ANON", default="60/min"),
    },
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_RESULT_EXPIRES = timedelta(days=1)

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", default="strict-origin-when-cross-origin")
CSP_REPORT_ONLY_ENABLED = env.bool("CSP_REPORT_ONLY_ENABLED", default=False)
CSP_REPORT_ONLY_POLICY = env(
    "CSP_REPORT_ONLY_POLICY",
    default=(
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "img-src 'self' data: https:; object-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'"
    ),
)

EMAIL_VERIFICATION_REQUIRED = env("EMAIL_VERIFICATION_REQUIRED")
LEGAL_TOS_VERSION = env("LEGAL_TOS_VERSION", default="1.0")
LEGAL_GUIDELINES_VERSION = env("LEGAL_GUIDELINES_VERSION", default="1.0")
ACCOUNT_DELETION_RETENTION_DAYS = env.int("ACCOUNT_DELETION_RETENTION_DAYS", default=30)
ACCOUNT_DEACTIVATION_RETENTION_DAYS = env.int("ACCOUNT_DEACTIVATION_RETENTION_DAYS", default=365)
ACCOUNT_PURGE_ENABLED = env.bool("ACCOUNT_PURGE_ENABLED", default=True)
ACCOUNT_PURGE_CRON_HOUR = env.int("ACCOUNT_PURGE_CRON_HOUR", default=3)
ACCOUNT_PURGE_CRON_MINUTE = env.int("ACCOUNT_PURGE_CRON_MINUTE", default=15)
MAIL_SERVER_HOST = env("MAIL_SERVER_HOST", default="")
MAIL_SERVER_IPV4 = env("MAIL_SERVER_IPV4", default="")
MAIL_SERVER_IPV6 = env("MAIL_SERVER_IPV6", default="")
REQUEST_SLOW_MS = env.int("REQUEST_SLOW_MS", default=700)
FEATURE_PM_E2E_ENABLED = env.bool("FEATURE_PM_E2E_ENABLED", default=False)
FEATURE_PM_DEV_CIPHERTEXT_PREVIEW = env.bool("FEATURE_PM_DEV_CIPHERTEXT_PREVIEW", default=False)
FEATURE_PM_WEBSOCKET_ENABLED = env.bool("FEATURE_PM_WEBSOCKET_ENABLED", default=False)
PM_CONVERSATION_CREATION_LIMIT = env.int("PM_CONVERSATION_CREATION_LIMIT", default=10)
PM_CONVERSATION_CREATION_WINDOW_SECONDS = env.int("PM_CONVERSATION_CREATION_WINDOW_SECONDS", default=86400)
PM_MESSAGE_RATE_LIMIT_MESSAGES = env.int("PM_MESSAGE_RATE_LIMIT_MESSAGES", default=100)
PM_MESSAGE_RATE_LIMIT_WINDOW_SECONDS = env.int("PM_MESSAGE_RATE_LIMIT_WINDOW_SECONDS", default=60)
PM_KEY_REGISTRATION_LIMIT = env.int("PM_KEY_REGISTRATION_LIMIT", default=5)
PM_KEY_REGISTRATION_WINDOW_SECONDS = env.int("PM_KEY_REGISTRATION_WINDOW_SECONDS", default=86400)
PM_KEY_ACK_COOLDOWN_SECONDS = env.int("PM_KEY_ACK_COOLDOWN_SECONDS", default=10)
PM_KEY_ROTATION_COOLDOWN_SECONDS = env.int("PM_KEY_ROTATION_COOLDOWN_SECONDS", default=300)
PM_PUBLIC_KEY_MIN_BYTES = env.int("PM_PUBLIC_KEY_MIN_BYTES", default=8)
PM_ATTACHMENT_MAX_FILES = env.int("PM_ATTACHMENT_MAX_FILES", default=5)
PM_ATTACHMENT_MAX_BYTES = env.int("PM_ATTACHMENT_MAX_BYTES", default=100 * 1024 * 1024)

# Encrypted DM uploads can be large multipart requests (ciphertext + files + manifest).
# Raise request/body parser limits so valid attachments do not fail with HTTP 400.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=128 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int("FILE_UPLOAD_MAX_MEMORY_SIZE", default=10 * 1024 * 1024)
FEATURE_LINK_UNFURL_ENABLED = env.bool("FEATURE_LINK_UNFURL_ENABLED", default=False)
FEATURE_INDEXED_HASHTAG_SEARCH_ENABLED = env.bool("FEATURE_INDEXED_HASHTAG_SEARCH_ENABLED", default=True)
FEATURE_FEDERATION_OUTBOUND_ENABLED = env.bool("FEATURE_FEDERATION_OUTBOUND_ENABLED", default=False)
FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED = env.bool("FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED", default=True)
ABUSE_VELOCITY_BLOCK_ENABLED = env.bool("ABUSE_VELOCITY_BLOCK_ENABLED", default=True)
ABUSE_MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST = env.int("ABUSE_MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST", default=7)
ABUSE_EMAIL_VERIFICATION_TRUST_BONUS = env.int("ABUSE_EMAIL_VERIFICATION_TRUST_BONUS", default=25)
ABUSE_RECENT_REPORT_PENALTY_PER_REPORT = env.int("ABUSE_RECENT_REPORT_PENALTY_PER_REPORT", default=10)
ABUSE_RECENT_ACTION_PENALTY_PER_ACTION = env.int("ABUSE_RECENT_ACTION_PENALTY_PER_ACTION", default=15)
ABUSE_TRUST_SCORE_THROTTLE_THRESHOLD = env.int("ABUSE_TRUST_SCORE_THROTTLE_THRESHOLD", default=30)
ABUSE_THRESHOLD_POSTS_PER_HOUR = env.int("ABUSE_THRESHOLD_POSTS_PER_HOUR", default=5)
ABUSE_THRESHOLD_FOLLOWS_PER_HOUR = env.int("ABUSE_THRESHOLD_FOLLOWS_PER_HOUR", default=10)
ABUSE_THRESHOLD_LIKES_PER_HOUR = env.int("ABUSE_THRESHOLD_LIKES_PER_HOUR", default=20)
ABUSE_THRESHOLD_REPOSTS_PER_HOUR = env.int("ABUSE_THRESHOLD_REPOSTS_PER_HOUR", default=10)
ABUSE_THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD = env.int("ABUSE_THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD", default=3)
ABUSE_THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD = env.int("ABUSE_THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD", default=4)
ABUSE_THROTTLE_RECENT_ACTIONS_DAYS = env.int("ABUSE_THROTTLE_RECENT_ACTIONS_DAYS", default=7)
ABUSE_THROTTLE_RECENT_REPORTS_DAYS = env.int("ABUSE_THROTTLE_RECENT_REPORTS_DAYS", default=3)
ABUSE_THROTTLE_POSTING_VELOCITY_HOURS = env.int("ABUSE_THROTTLE_POSTING_VELOCITY_HOURS", default=1)
ABUSE_THROTTLE_LOW_TRUST_HOURS = env.int("ABUSE_THROTTLE_LOW_TRUST_HOURS", default=6)
ABUSE_PROFILE_AVATAR_TRUST_BONUS = env.int("ABUSE_PROFILE_AVATAR_TRUST_BONUS", default=10)
ABUSE_PROFILE_BIO_TRUST_BONUS = env.int("ABUSE_PROFILE_BIO_TRUST_BONUS", default=8)
ABUSE_HAS_POSTS_TRUST_BONUS = env.int("ABUSE_HAS_POSTS_TRUST_BONUS", default=5)
ABUSE_HAS_LIKED_TRUST_BONUS = env.int("ABUSE_HAS_LIKED_TRUST_BONUS", default=5)
ABUSE_HAS_FOLLOWERS_TRUST_BONUS = env.int("ABUSE_HAS_FOLLOWERS_TRUST_BONUS", default=10)
ABUSE_HAS_FOLLOWING_TRUST_BONUS = env.int("ABUSE_HAS_FOLLOWING_TRUST_BONUS", default=5)
DEAD_LETTER_REPLAY_MAX_COUNT = env.int("DEAD_LETTER_REPLAY_MAX_COUNT", default=5)
DEAD_LETTER_REPLAY_COOLDOWN_SECONDS = env.int("DEAD_LETTER_REPLAY_COOLDOWN_SECONDS", default=300)
FEDERATION_SHARED_SECRET = env.str("FEDERATION_SHARED_SECRET", default="")
FEDERATION_SIGNATURE_MAX_AGE_SECONDS = env.int("FEDERATION_SIGNATURE_MAX_AGE_SECONDS", default=300)

if ACCOUNT_PURGE_ENABLED:
    CELERY_BEAT_SCHEDULE = {
        "accounts-purge-expired": {
            "task": "apps.accounts.tasks.purge_expired_accounts_task",
            "schedule": crontab(hour=ACCOUNT_PURGE_CRON_HOUR, minute=ACCOUNT_PURGE_CRON_MINUTE),
        }
    }
