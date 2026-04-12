# Freeparty Operations Runbook

This runbook describes day-1 operations and troubleshooting for the Freeparty foundation.

## 1. Services

Expected services in Compose:
- web (Daphne / ASGI)
- db (PostgreSQL)
- redis
- celery_worker
- celery_beat
- mailhog (local email server for testing)

## 2. Local Email Testing with MailHog

When developing locally, all emails are captured by MailHog instead of being sent to external servers. No configuration needed.

**Access MailHog Web UI:**
- Open http://localhost:8025 in your browser
- All emails sent by the app (verification, password reset, notifications) appear here
- Click any email to view full headers and body
- Emails are captured in memory (cleared on container restart)

**How it works:**
- Django is configured to send mail to `mailhog:1025` (SMTP port)
- MailHog intercepts and stores all messages
- MailHog Web UI runs on port 8025

**Testing email flows:**
1. Trigger email action (sign up, password reset, etc.)
2. Check MailHog at http://localhost:8025
3. Extract any tokens/links for testing (e.g., verification token, reset link)
4. Click links directly or paste into browser

**No additional setup needed** — MailHog starts automatically with `docker compose up`.

## 3. Health Checks

Web health endpoints:
- `GET /health/live/`
- `GET /health/ready/`

API health endpoints:
- `GET /api/v1/health/live/`
- `GET /api/v1/health/ready/`

Interpretation:
- `live`: process is running.
- `ready`: DB + cache are available.

## 4. Startup Sequence

1. Start infra and app.
2. Verify readiness endpoint returns status `ok`.
3. Confirm migrations are current.
4. Confirm Celery worker and beat process are alive.

## 5. Incident Triage Quick Guide

### App returns 500
- Check app logs.
- Call `/health/ready/` and `/api/v1/health/ready/`.
- If DB/cache checks fail, inspect dependent service logs.

### Background tasks not processing
- Verify `celery_worker` is up.
- Check Redis availability.
- Confirm broker/backend URLs in environment.

### Moderation workflow issues
- Confirm moderator user has `is_staff=True`.
- Access `/moderation/` and verify report queue renders.
- Use report detail page to update status and record notes/actions.

## 6. Deployment Notes

- Behind Apache reverse proxy to Daphne.
- Enable websocket proxying for `/ws/` paths.
- Serve static/media via Apache or object storage/CDN.
- Ensure trusted proxy headers are configured safely.

## 6. Routine Maintenance

- Rotate secrets and SMTP credentials.
- Apply security updates to base images and dependencies.
- Run Django checks and tests before releases.

Commands:

```bash
python manage.py check
python manage.py test
```

## 7. Recovery Checklist

- Restore DB backup.
- Re-run migrations.
- Verify health endpoints.
- Validate login, post creation, notifications, and moderation dashboard.
