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
	- `apps.accounts.tasks.send_password_reset_email`
	- `apps.accounts.tasks.send_password_reset_notice`
	- `apps.accounts.tasks.send_system_email`
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

### Dead-letter replay decision tree (Phase 7.2)
- Use `python manage.py dead_letter_inspect --limit 25` to review recent terminal failures.
- Use `python manage.py dead_letter_inspect --task <task-name> --terminal-only` when isolating one worker path.
- Replay only when all three conditions are true:
	- root cause has been removed
	- payload is safe to re-run with its idempotency key
	- target system is healthy again
- Dismiss or leave parked when payload is stale, unsafe, or tied to user-visible state that already recovered manually.
- Replay command:
	- `python manage.py dead_letter_inspect --replay <failure-id>`
- Replay audit expectations:
	- `AsyncTaskFailure.terminal_reason` becomes `manual_replay`
	- payload replay counter increments
	- worker logs should emit the normal `task_start` and `task_success` or a new terminal record

### Media processing reliability workflow (Phase 4.3)
- Media attachments are processed asynchronously by `apps.posts.tasks.process_media_attachment`.
- Failed media jobs can be re-queued with:
	- `python manage.py reprocess_failed_media --limit 100`
- Command behavior:
	- selects attachments with `processing_state=failed`
	- sets them back to `pending`
	- enqueues a new processing task run with a unique idempotency suffix

### Media moderation workflow (Phase 4.4)
- Staff can transition attachment moderation state via API:
	- `POST /api/v1/moderation/attachments/{id}/state/`
	- payload: `{ "moderation_state": "normal|flagged|removed", "notes": "..." }`
- Staff can also moderate attachments from moderation report detail UI:
	- `/moderation/reports/{id}/` -> "Post Attachments" section
- Enforcement baseline:
	- non-staff post API responses only include attachments with `moderation_state=normal`
	- staff post API responses include all attachment moderation states
- Moderation report detail API now includes attachment context:
	- `target_post_attachments` in `GET /api/v1/moderation/reports/{id}/`

### PM + E2E foundation operations (Phase 4.5)
- PM service pathways are disabled by default using `FEATURE_PM_E2E_ENABLED=False`.
- Before enabling in any environment:
	1. Complete checklist in `docs/adr/0001-pm-e2e-foundation.md`.
	2. Confirm no plaintext PM fields or debug logs are emitted in app/worker logs.
	3. Run PM test suite and system checks.
- PM persistence contract in this slice is encrypted envelope only:
	- `ciphertext`
	- `message_nonce`
	- sender/recipient key ids
- Development-only ciphertext preview:
	- `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=True` only takes effect when `DEBUG=True`.
	- Use only for local debugging; keep disabled in shared/staging/production environments.

### Report reason taxonomy hardening (Phase 5/6 planning)
- Introduce structured report reasons for high-risk categories (for example DMCA/IP, posting of a minor, death/severe injury graphic media).
- Assign escalation rules and response-time targets per category.
- Capture category-specific evidence fields to improve legal/compliance handling.

### DM initiation workflow (Phase 5 kickoff)
- Feature-gated HTML DM shell routes:
	- `GET /messages/`
	- `POST /messages/start/{handle}/`
	- `GET /messages/{id}/`
	- `POST /messages/{id}/send/`
- If `FEATURE_PM_E2E_ENABLED=False`, DM views intentionally render disabled state or reject initiation.
- Start flow protections:
	- self-DM blocked
	- blocked-account DM blocked
	- existing direct conversations are reused
- Send flow protections:
	- only direct conversations supported
	- sender must be a participant
	- both participants need active identity keys
	- stored envelopes remain metadata-only in HTML rendering

### Key change warning workflow (Phase 5.3)
- DM detail warns when the current remote active key differs from the last acknowledged remote key for that conversation participant.
- Operators/testers can validate this by rotating or replacing a participant's active `UserIdentityKey` and reloading the conversation detail page.
- Acknowledgment behavior:
	- `POST /messages/{id}/acknowledge-key/`
	- stores the current remote key id and acknowledgment timestamp on the participant record

### Identity key bootstrap workflow (Phase 5.3 follow-up)
- When a user has no active key, UI provides a bootstrap action:
	- `POST /messages/keys/bootstrap/`
- Successful bootstrap creates an active `UserIdentityKey` for the current actor.
- Optional `next` form value can return user to DM detail after bootstrap.

### Browser key registration and decrypt-on-read workflow (Phase 5.6)
- Browser registration endpoint:
	- `POST /messages/keys/register/`
	- payload: `key_id`, `public_key`, `fingerprint_hex`
- Security contract:
	- server stores public key material only
	- browser private key remains local (localStorage)
- Operational implications:
	- clearing browser storage removes local private keys for that device
	- envelopes tied to removed local keys will remain stored but cannot be decrypted on that device

### Device/key inventory and recovery workflow (Phase 6.4)
- DM detail now includes an explicit **Device & Key Inventory** section:
	- recent server-side local keys
	- recent remote participant keys
	- currently acknowledged remote key id
	- browser-private-key availability status for this device
- Recovery guidance:
	- if browser private key material is missing for an active server key, use **Generate browser keypair for this device**
	- this rotates server active key state for that actor and requires safety-fingerprint re-verification
	- key-change warning remains the authoritative signal before trusting new encrypted messages

### SMTP structured delivery observability (Phase 6.6)
- Account email tasks now emit structured `smtp_delivery` logs for:
	- `event=attempt`
	- `event=success`
	- `event=failure`
	- `event=retry_scheduled`
- Logged fields include:
	- `task`, `task_id`, `correlation_id`
	- `recipient_count`, `attempt`, `max_retries`, `will_retry`
	- `error` (for failures/retries)

### Async interaction and DM poll metrics (Phase 6.6)
- Structured `interaction_metric` logs now cover:
	- async social JSON actions (follow/unfollow/like/repost/bookmark/follow-request approve/reject)
	- DM updates polling endpoint (`GET /messages/{id}/updates/`)
- Logged fields include:
	- `name`, `success`, `duration_ms`, `status_code`
	- `actor_id`, `target_id`, `detail`

### Alert thresholds and escalation guidance (Phase 6.6)
- Suggested alerts for new telemetry:
	- `smtp_delivery event=failure`: >= 5 failures in 10 minutes
	- `smtp_delivery event=retry_scheduled`: >= 10 retries in 10 minutes
	- `interaction_metric name=dm_conversation_updates success=False`: >= 20 failures in 10 minutes
	- `interaction_metric name=social_* success=False`: >= 50 failures in 10 minutes
	- `interaction_metric name=dm_conversation_updates duration_ms`: p95 > 1500 ms for 15 minutes
	- `interaction_metric name=social_* duration_ms`: p95 > 800 ms for 15 minutes
- Escalation sequence:
	1. Correlate request IDs and `correlation_id` values in app + worker logs.
	2. If SMTP failures spike, run `python manage.py check_smtp` and verify upstream relay/auth.
	3. If social/DM latency spikes, check DB/cache readiness endpoints and lock contention.
	4. If retry storms persist >30 minutes, page on-call and shift to degraded mode guidance.

### PM staged rollout and gate closure (Phase 7.0)
- PM feature is now controlled by staged rollout via `PMRolloutPolicy` model (in addition to `FEATURE_PM_E2E_ENABLED` flag).
- Rollout stages managed in Django admin:
	- `DISABLED`: All actors denied (default). Set `FEATURE_PM_E2E_ENABLED=False` to enforce at app level.
	- `ALLOWLIST`: Only explicitly allowlisted actors can use PM. Manage via admin "Allowlisted Actors" M2M.
	- `BETA`: All authenticated users can opt-in to PM (requires explicit feature flag + stage).
	- `GENERAL`: Full rollout; all authenticated users can use PM.
- **Staged rollout workflow:**
	1. Start in `DISABLED` stage while security gate closure is in progress.
	2. Move to `ALLOWLIST` stage when ready for internal alpha (ops + early testers).
	3. Move to `BETA` stage when threat model gate is signed off and beta cohort is defined.
	4. Move to `GENERAL` stage when public beta is approved.
- **PM rollback procedure (if incident detected):**
	1. Immediately set `FEATURE_PM_E2E_ENABLED=False` in environment and redeploy.
	2. Set `PMRolloutPolicy.stage=DISABLED` in admin console.
	3. Monitor logs for active PM connections gracefully closing.
	4. No data loss — conversations and encrypted envelopes are preserved.
	5. Document incident and root cause in security runbook before re-enabling.
- **Incident response for PM security issues:**
	- If plaintext leakage detected in logs: Revert `FEATURE_PM_E2E_ENABLED`, audit logs for sensitive data, escalate to security team.
	- If key compromise/loss detected: Trigger key rotation workflow; affected user must acknowledge new key before messaging resumes.
	- If message ordering/replay issue detected: Halt PM writes (disable feature flag), inspect `EncryptedMessageEnvelope` table for integrity.
	- If unacknowledged key mismatch causes false warnings: Revert `FEATURE_PM_WEBSOCKET_ENABLED` if using websocket updates; fall back to polling interval.
- **PM messaging is disabled-by-default within views:**
	- All PM routes (`/messages/`) check both `FEATURE_PM_E2E_ENABLED` flag AND `is_actor_pm_eligible()` function.
	- Eligible actors are determined by: global feature flag + staged rollout policy + optional per-actor allowlist.
	- If ineligible, HTTP response is 403 Forbidden with message "Private messaging is not available to your account."

### Phase 7 kickoff posture
- Current planning baseline is documented in:
	- `phases_phase_7.md` (full roadmap)
	- `PHASE_7_KICKOFF.md` (operator-facing kickoff checklist)
- Phase 7 risk controls:
	- keep `FEATURE_PM_E2E_ENABLED` disabled by default outside explicit rollout windows
	- keep `FEATURE_PM_WEBSOCKET_ENABLED` disabled until websocket failure drills are complete
	- keep `FEATURE_LINK_UNFURL_ENABLED` disabled until outbound fetch policy and alerting are validated in target environment
- During Phase 7 execution, require an explicit rollback note in each change set touching:
	- feature flags
	- migrations
	- async task retry/dead-letter behavior
	- federation delivery configuration

### Structured log quick filters
- SMTP delivery events:
	- search for `smtp_delivery` and group by `event` (`attempt`, `success`, `failure`, `retry_scheduled`)
- Async interaction events:
	- search for `interaction_metric` and group by `name` + `success`
- Request correlation:
	- use `request_id` (web) and `correlation_id` (worker tasks) to join timelines during incident triage

### Structured report intake workflow (Phase 5 kickoff)
- Actor/post report entry points now route to a dedicated report form page.
- Stored report severity is derived from selected reason category.
- Current severity expectations:
	- `critical`: posting of a minor, non-consensual intimate media
	- `high`: DMCA/IP, graphic death/injury, impersonation
	- `medium`: harassment, other
	- `low`: spam/scam

### Moderation queue routing filters (Phase 5.4)
- Dashboard supports additional filters:
	- severity
	- reason category
- Staff report API supports equivalent query params:
	- `severity`
	- `reason_category`
- Use these filters during incident surge windows to prioritize high/critical safety queues first.

### Moderation escalation and SLA workflow (Phase 7.3)
- `Report` now tracks:
	- `assigned_to`
	- `first_assigned_at`
	- `responded_at`
	- `sla_target_minutes`
	- `evidence_hash`
- Critical intake auto-assignment:
	- critical reports are automatically assigned to the earliest-created staff account
	- web logs emit `incident_escalation` with report id and assignee
- Staff dashboard triage additions:
	- `owner_state=assigned|unassigned`
	- `sla_breached=true`
- SLA analytics:
	- `GET /moderation/reports/analytics/sla/`
	- `GET /api/v1/moderation/reports/analytics/sla/`
- Evidence guardrail:
	- high/critical reports cannot change state without evidence notes or an existing evidence hash
	- status/action notes stamp a deterministic `evidence_hash` for later review

### Federation pilot allowlist and outbound delivery (Phase 7.4/7.5)
- Instance controls now include:
	- `allowlist_state=pending|allowed|blocked`
	- `allowlist_reason`
	- optional per-instance metadata keys: `shared_secret`, `inbox_url`
- Inbound pilot contract:
	- only `allowlist_state=allowed` and not-blocked domains may be fetched
	- inbound actor/object payloads require a valid `X-Freeparty-Timestamp` + `X-Freeparty-Signature`
	- fetched entities are stored as `RemoteActor` and `RemotePost`
- Outbound pilot contract:
	- protected by `FEATURE_FEDERATION_OUTBOUND_ENABLED=False` by default
	- worker signs POST bodies with `X-Freeparty-Key-Id`, `X-Freeparty-Timestamp`, `X-Freeparty-Signature`
	- retry schedule: 1m, 5m, 30m, 2h, then terminal failure
- Required configuration before enabling outbound:
	- set `FEATURE_FEDERATION_OUTBOUND_ENABLED=True`
	- set `FEDERATION_SHARED_SECRET` or per-instance `metadata.shared_secret`
	- define partner inbox URL in `Instance.metadata.inbox_url` when not using the default `https://<domain>/inbox`

### Phase 7.6 alert ownership baseline
- Platform on-call owns:
	- HTTP 5xx spikes
	- SMTP delivery degradation
	- Redis/database availability issues
- Backend on-call owns:
	- task failure rate spikes
	- dead-letter growth
	- DM poll latency regressions
- Federation owner owns:
	- federation delivery backlog growth
	- signature validation failures
	- pilot partner onboarding/offboarding

### Phase 7.7 failure-drill checklist
- Redis down:
	- confirm API degradation mode
	- confirm worker enqueue/retry visibility
	- capture time-to-detect and time-to-mitigate
- SMTP relay down:
	- confirm `smtp_delivery event=failure|retry_scheduled`
	- inspect dead-letter queue after retry ceiling
- Database lag:
	- confirm readiness failures and user-visible degradation messaging
- DM websocket disruption:
	- confirm polling remains available while websocket flag stays disabled
- Federation delivery storm:
	- inspect retry queue, backlog, and terminal failures before replaying anything

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
