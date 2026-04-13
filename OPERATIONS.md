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
- Use dashboard filters (status/reason/reporter/target/post/date) to triage queue quickly.
- Use quick status buttons for fast state transitions.
- Use report detail page to record action + internal note when deeper review is needed.
- Confirm report status updates stamp reviewer and review timestamp.

### Notification workflow issues
- Use `/notifications/` filters (`all`, `unread`, type filters) and view mode toggle (`flat`/`grouped`) to validate visibility.
- Validate single mark-read and mark-all-read behaviors.
- API checks:
	- `GET /api/v1/notifications/`
	- `POST /api/v1/notifications/{id}/mark-read/`
	- `POST /api/v1/notifications/mark-all-read/`

### Request tracing and latency triage
- Every response includes `X-Request-ID` for log and client correlation.
- Request observability middleware emits:
	- `request_complete` (method/path/status/duration/request_id/user_id)
	- `request_error` (method/path/duration/request_id/user_id + stack trace)
- If request latency exceeds `REQUEST_SLOW_MS` (default `700` ms), the app logs a `slow_request` warning.
- During incident analysis, capture the `X-Request-ID` from response headers and search app logs for matching entries.

### Celery task tracing and failure triage
- Shared helper `apps.core.services.task_observability.observe_celery_task` emits:
	- `task_start` (task/task_id/correlation_id)
	- `task_success` (task/task_id/duration_ms/correlation_id)
	- `task_failure` (task/task_id/duration_ms/correlation_id + stack trace)
- Initial instrumented tasks:
	- `apps.accounts.tasks.send_verification_email`
	- `apps.accounts.tasks.send_password_reset_notice`
	- `apps.notifications.tasks.process_notification_fanout`
	- `apps.federation.tasks.execute_federation_delivery`
- For incident triage:
	1. Capture request `X-Request-ID` from client/API logs.
	2. Search app logs for `request_complete` / `request_error` with that id.
	3. Search worker logs for `task_*` entries with matching `correlation_id`.

### Async terminal failure review workflow (Phase 3.4)
- Reliability events are captured in:
	- `apps.core.models.AsyncTaskExecution`
	- `apps.core.models.AsyncTaskFailure`
- Use management command to inspect failures:
	- `python manage.py async_failures --limit 25`
	- `python manage.py async_failures --terminal-only`
	- `python manage.py async_failures --task federation_delivery --terminal-only`
- Suggested incident sequence:
	1. Check terminal failures with `--terminal-only`.
	2. Group by `task` and `error` message.
	3. Use `corr=` value to correlate with web/worker logs.
	4. Address root cause and manually re-enqueue only affected payloads.

### Initial SLO Targets (Phase 3 baseline)
| Objective | Target | Alert Trigger | Scope |
|---|---|---|---|
| HTTP latency (p95) | <= 700 ms | > 700 ms sustained for 15 min | Web app requests |
| HTTP error rate (5xx) | < 1.0% | >= 2.0% for 10 min | Web app requests |
| Queue lag (Celery) | < 60 sec typical | >= 300 sec for 10 min | Default queue |
| Task failure rate | < 2.0% | >= 5.0% for 10 min | Instrumented Celery tasks |

Notes:
- These are initial baseline targets and should be tuned with production data.
- Keep thresholds environment-driven when possible.
- These are initial baseline targets and should be tuned with production data.
- Keep thresholds environment-driven when possible.

## 5b. Anti-Abuse and Trust Signals (Phase 3)

Trust signals are computed per actor to support adaptive throttling and staff investigation of abuse patterns.

### Trust Signal Components

Each actor's trust signal includes:
- **account_age_days**: Days since account creation
- **email_verified**: Boolean flag
- **recent_reports_count**: Reports filed against actor (last 30 days)
- **recent_actions_count**: Moderation actions taken (last 30 days)
- **posts_last_hour**: Post velocity signal
- **follows_last_hour**: Follow velocity signal
- **likes_last_hour**: Like velocity signal
- **reposts_last_hour**: Repost velocity signal
- **trust_score**: Computed 0-100 scale (higher = more trustworthy)
- **is_throttled**: Boolean; true if `trust_score < 30`
- **throttle_reason**: String (e.g., `recent_moderation_actions`, `posting_velocity`)
- **throttled_until**: Datetime when throttle expires

### Trust Score Computation

Baseline score: 50

Adjustments (applied in order):
1. **Account age bonus**: +1 per 3 days of age (capped at +20)
2. **New account penalty**: If age < 7 days, -15
3. **Email verification bonus**: +25 if verified; -10 if not
4. **Recent reports penalty**: -10 per report (last 30 days)
5. **Recent actions penalty**: -15 per action (last 30 days)
6. **Velocity penalties**:
   - Posts >= 5/hour: -20
   - Follows >= 10/hour: -15
   - Likes >= 20/hour: -10
   - Reposts >= 10/hour: -15

Final score clamped to 0-100.

### Throttling Policy

When `trust_score < 30`, actor is throttled with a context-specific reason and expiration:
- `recent_moderation_actions` (>2 actions): 7-day throttle
- `recent_reports` (>3 reports): 3-day throttle
- `posting_velocity` (>= 5 posts/hour): 1-hour throttle
- `low_trust_score` (generic fallback): 6-hour throttle

Staff can inspect trust signals via moderation report detail API at `GET /api/v1/moderation/reports/{id}/` (includes `target_actor_trust_signal`).

### Usage

**Compute or refresh signal:**
```python
from apps.moderation.services import TrustSignalService
signal = TrustSignalService.compute_trust_signal(actor)
```

**Check if actor should be throttled:**
```python
should_throttle, reason, until = TrustSignalService.should_throttle(actor)
if should_throttle:
	# Apply action-specific cooldown or rate limit
	pass
```

**Record velocity event:**
```python
from apps.moderation.services import ActionVelocityTracker
ActionVelocityTracker.record_post(actor)  # After post creation
```

## 5c. Security Audit Events (Phase 3)

Security audit events log forensically sensitive actions for compliance and incident investigation.

### Audit Event Types

- `login_success`: Successful login (IP, user agent)
- `login_failure`: Failed login attempt (IP, reason)
- `password_reset_request`: User requested password reset
- `password_reset_complete`: User completed password reset
- `email_verification`: User verified email address
- `email_changed`: User changed email address (old email captured)
- `moderator_privilege_grant`: User granted moderator privileges
- `moderator_privilege_revoke`: User had moderator privileges removed
- `moderation_action_create`: Moderator created a moderation action

### Access Audit Events

**Query events for a user:**
```python
from apps.moderation.models import SecurityAuditEvent
events = SecurityAuditEvent.objects.filter(user=user).order_by('-created_at')[:20]
```

**Query events by type:**
```python
login_events = SecurityAuditEvent.objects.filter(
	event_type=SecurityAuditEvent.EventType.LOGIN_SUCCESS
).order_by('-created_at')[:50]
```

**Export for compliance:**
All events include:
- `event_type`
- `user_id`
- `ip_address` (when available)
- `user_agent` (when available)
- `details` (JSON with event-specific context)
- `created_at` (auto-stamped, indexed)

Periodic backups and exports are recommended per your compliance requirements.

## 6. Deployment Notes

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
