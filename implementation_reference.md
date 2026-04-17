# Freeparty Implementation Reference

This document complements [foundation.md](foundation.md) with practical implementation decisions, conventions, and next-phase priorities.

## 1. Architecture Decisions

- Centralized-first runtime with federation-ready schemas.
- UUID primary keys across core entities for stable distributed references.
- Canonical URIs are generated from `SITE_URL` and stored on actors/posts.
- Actor identity is decoupled from account authentication.
- Rate-limited endpoints are enabled where abuse risk is highest.

## 2. Operational Endpoints

- Liveness: `/health/live/`
- Readiness: `/health/ready/`

Readiness checks currently verify:
- DB query execution (`SELECT 1`)
- Cache read/write (Redis-backed in production)

## 3. Security and Abuse Baseline

Implemented baseline:
- Django password hashing + CSRF/session protections
- Production security flags in `config.settings.production`
- Redis-backed request throttling via `django-ratelimit`
- Account state model for moderation (`active`, `limited`, `suspended`)

Recommended next hardening:
- Add explicit trusted proxy CIDR guidance and middleware checks
- Add audit trail model for security-sensitive account events
- Add object-level permissions for moderator-only APIs

## 4. Service Layer Conventions

- Keep feed logic in `apps.timelines.services`, not views.
- Keep relationship logic in `apps.social.services`.
- Keep URI generation in `apps.core.services.uris`.
- Keep token signing/verification in `apps.accounts.services`.
- Keep object-level social permissions in `apps.core.permissions`.
- Keep reusable timeline/search query constraints in selector modules (`apps.posts.selectors`).

### Permission Policy Contract (Phase 2)

Use these helpers instead of ad-hoc checks in views/API code:

- `can_view_post`
- `can_edit_post`
- `can_delete_post`
- `can_comment_on_post`
- `can_edit_comment`
- `can_delete_comment`
- `can_view_actor`
- `can_follow_actor`

Rules covered by these helpers:

- ownership checks
- soft-deleted object restrictions
- moderation visibility restrictions
- blocked relationship restrictions
- follower-only visibility logic

### Private Account Convention

- `profiles.Profile.is_private_account` controls account-level privacy.
- When private mode is enabled:
	- `follow_actor` creates/updates relation state to `pending`
	- profile visibility is restricted to accepted followers and owner
	- post visibility is restricted to accepted followers and owner
- Follow request lifecycle endpoints:
	- HTML: `/social/follow-requests/`
	- API: `/api/v1/follows/incoming/`, `/api/v1/follows/{id}/approve/`, `/api/v1/follows/{id}/reject/`

### Moderation Workflow Convention

- Report queue triage happens through:
	- dashboard filters (status/reason/reporter/target type/post/date)
	- quick status transitions from queue rows
	- report detail update form for full action + notes
- Report status now supports: `open`, `under_review`, `actioned`, `resolved`, `dismissed` (+ legacy `reviewing`).
- Any report mutation that changes status should stamp `reviewed_by` and `reviewed_at`.

### Notifications Convention

- Use `apps.notifications.services.create_notification_if_new` for event notifications to reduce duplicate spam.
- Notification read operations supported in both HTML and API:
	- HTML: single mark-read + mark-all-read
	- API: `POST /api/v1/notifications/{id}/mark-read/` and `POST /api/v1/notifications/mark-all-read/`
- Notification UI supports optional grouped mode (`?view=grouped`) for low-noise inbox scanning.
- Notification rows should include source context when available:
	- source actor handle
	- source post link/snippet
	- payload summary text for quick triage

### Observability Convention (Phase 3 Kickoff)

- `apps.core.middleware.RequestObservabilityMiddleware` is responsible for baseline request tracing.
- Correlation policy:
	- preserve inbound `X-Request-ID` when provided
	- generate new request id when missing
	- include `X-Request-ID` on all responses
- Latency policy:
	- emit `slow_request` warning logs when request time >= `REQUEST_SLOW_MS`
	- tune `REQUEST_SLOW_MS` per environment without code changes
- Request log policy:
	- emit `request_complete` with method/path/status/duration/request_id/user_id
	- emit `request_error` with request correlation context on unhandled exceptions

### Celery Task Observability Convention

- Use `apps.core.services.task_observability.observe_celery_task` in task bodies.
- Emit standardized lifecycle logs:
	- `task_start`
	- `task_success`
	- `task_failure`
- Include `correlation_id` when task is triggered from a request/flow that already has one.
- Account transactional email tasks currently using this convention:
	- `apps.accounts.tasks.send_verification_email`
	- `apps.accounts.tasks.send_password_reset_email`
	- `apps.accounts.tasks.send_password_reset_notice`
	- `apps.accounts.tasks.send_system_email`

### Celery Reliability Convention (Phase 3.4)

- Use `apps.core.services.task_reliability` for idempotency and failure capture on critical tasks.
- Core models:
	- `apps.core.models.AsyncTaskExecution`: tracks idempotency key, attempts, status, and last error details.
	- `apps.core.models.AsyncTaskFailure`: captures each failure event with attempt/max_retries and terminal marker.
- Pattern for reliable task implementation:
	1. Build deterministic idempotency key (for example `federation_delivery:{delivery_id}`).
	2. Call `start_task_execution(...)` and return early when `should_skip` is true.
	3. Execute task body.
	4. Call `mark_task_execution_succeeded(...)` on success.
	5. Call `mark_task_execution_failed(...)` in `except` block before re-raising.
- Initial integration is implemented in `apps.federation.tasks.execute_federation_delivery`.

### Moderation Staff API Convention (Phase 3.2)

- Staff-only moderation report endpoints are served under `/api/v1/moderation/reports/`.
- Core actions:
	- queue list + filters
	- report detail
	- status transition
	- action creation
	- moderator note creation
- All mutating actions must stamp `reviewed_by`/`reviewed_at` or equivalent audit fields.

### Private Messaging Foundation Convention (Phase 4.5)

- PM foundation models live in `apps.private_messages` and currently include:
	- `Conversation`
	- `ConversationParticipant`
	- `UserIdentityKey`
	- `EncryptedMessageEnvelope`
- PM runtime writes are feature-gated by `FEATURE_PM_E2E_ENABLED` (default disabled).
- PM service methods must call `require_private_messages_enabled()` before mutating data.
- Message storage contract is encrypted-envelope-only:
	- required: ciphertext, message nonce, sender key id, recipient key id
	- forbidden: plaintext message persistence path
- `key_epoch` on envelopes is reserved for ratchet/session-key lifecycle slices.
- Rollout gate reference: `docs/adr/0001-pm-e2e-foundation.md`.
- Verification contract (slice 2 delivered):
	- `compute_safety_fingerprint_hex(local_fp, remote_fp)` -> deterministic 64-char hex digest
	- `compute_identicon_seed(local_fp, remote_fp)` -> deterministic 32-char visual seed
	- both contracts are order-invariant across participants by canonicalized sorted input
	- HTML kickoff routes delivered in Phase 5:
		- `/messages/`
		- `/messages/start/{handle}/`
		- `/messages/{conversation_id}/`
		- `POST /messages/{conversation_id}/send/`
	- Use `get_or_create_direct_conversation(...)` for direct-thread reuse instead of creating duplicates.
	- Use `send_direct_encrypted_message(...)` for direct-thread envelope storage so participant and active-key checks remain centralized.
	- Conversation HTML must remain metadata-only; do not render stored ciphertext back into page content.
	- Optional development preview:
		- `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=True` plus `DEBUG=True` allows raw ciphertext visibility in DM detail for local debugging only.
		- Do not enable this preview in non-debug environments.
	- Browser crypto workflow (Phase 5.6):
		- `POST /messages/keys/register/` accepts browser-generated `key_id`, `public_key`, `fingerprint_hex` and rotates active key.
		- private key remains browser-local and must never be submitted to backend.
		- DM detail encrypts plaintext in browser and submits only ciphertext + nonce.
		- DM detail decrypts stored envelopes in browser when local private key exists for message key id.
	- Key-change warning contract:
		- `ConversationParticipant.acknowledged_remote_key_id` stores the last accepted remote key id for that participant in that conversation
		- `ConversationParticipant.acknowledged_remote_key_at` stores the acknowledgment timestamp
		- show warning when current remote active key id differs from the acknowledged remote key id
	- Identity key bootstrap contract:
		- use `POST /messages/keys/bootstrap/` for local key generation when none exists
		- use `ensure_active_identity_key(...)` service helper to centralize creation/rotation behavior

### Report Reason Taxonomy Hardening Convention (Phase 5/6 Planning)

- Expand report reasons from freeform-only input toward policy-backed categories.
- Initial high-priority categories should include:
	- DMCA/IP complaint
	- posting of a minor
	- death or severe injury graphic media
	- non-consensual intimate media
	- impersonation
	- harassment
	- spam/scam
- Route high-severity categories to expedited moderation queues with explicit SLA/ownership.
- Current kickoff implementation stores derived severity on `moderation.Report.severity` using low/medium/high/critical.
- Moderation routing implementation now supports dashboard and API filtering by:
	- `severity`
	- `reason_category`

- All mutating actions must stamp `reviewed_by`/`reviewed_at` or equivalent audit fields.

### Trust Signals and Adaptive Throttling Convention (Phase 3.3)

Trust signals are per-actor signals used for abuse detection and adaptive throttling recommendations.

**Model**: `apps.moderation.models.TrustSignal` (one-to-one with Actor)
- Account age, email verification status, recent report/action counts
- Velocity counters (posts/follows/likes/reposts per hour)
- Computed trust_score (0-100; higher = more trustworthy)
- Throttle status with context-specific reason and expiration

**Service**: `apps.moderation.services.TrustSignalService`
- `compute_trust_signal(actor)`: Calculate/update trust score with configurable thresholds
- `get_trust_signal(actor)`: Fetch or compute (lazy initialization)
- `should_throttle(actor)`: Check current throttle status and auto-expire stale throttles

**Service**: `apps.moderation.services.ActionVelocityTracker`
- `record_post(actor)`: Update hourly post velocity counter
- `record_follow(actor)`: Update hourly follow velocity counter
- `record_like(actor)`: Update hourly like velocity counter
- `record_repost(actor)`: Update hourly repost velocity counter
- `is_velocity_anomaly(actor, action_type)`: Check if action would exceed threshold

**Staff visibility**:
- Trust signal summary is included in moderation report detail API as `target_actor_trust_signal`
- Shows computed scores, velocity signals, and throttle status/reason
- Staff can use this to understand why an actor is flagged

**Configuration thresholds** (tunable):
- Minimum account age for trust bonus: 7 days
- Velocity thresholds: 5 posts/hour, 10 follows/hour, 20 likes/hour, 10 reposts/hour
- Throttle trigger: trust_score < 30
- Throttle durations: 7 day (actions), 3 days (reports), 1 hour (velocity), 6 hours (generic)

### Security Audit Events Convention (Phase 3.3)

Security audit events log forensically important account and moderator actions.

**Model**: `apps.moderation.models.SecurityAuditEvent`
- Records user, event type, IP address (when available), user agent, context JSON
- Auto-indexed by user/event_type for fast queries

**Service**: `apps.moderation.services.SecurityAuditService`
- `log_login_success(user, ip, ua)`: Record successful login
- `log_login_failure(user, ip, ua, reason)`: Record failed login attempt
- `log_password_reset_request(user, ip, ua)`: Record password reset initiated
- `log_password_reset_complete(user, ip, ua)`: Record password reset completed
- `log_email_verification(user, ip, ua)`: Record email verification
- `log_email_changed(user, old_email, ip, ua)`: Record email change
- `log_moderator_action(moderator, target, action_type, ip, ua)`: Record moderator action

**Integration points**:
- `apps.accounts.views.RateLimitedLoginView`: Logs login success/failure
- `apps.accounts.views.RateLimitedPasswordResetView`: Logs reset request
- `apps.accounts.views.RateLimitedPasswordResetConfirmView`: Logs reset completion
- `apps.accounts.views.verify_email_view`: Logs email verification

**Staff query**:
- Export audit events via admin panel or management command for compliance
- Query by user or event type for incident investigation

## 5. Suggested Next Milestones

### Milestone A: PM Security Gate Closure (Phase 7.0/7.1)
- Convert PM security checklist into tracked closure tasks with ownership.
- Add staged PM rollout controls and rollback criteria.
- Harden key lifecycle policy for abusive or high-frequency key resets.

### Milestone B: Async Reliability Maturity (Phase 7.2)
- Extend reliability wrappers and dead-letter visibility to remaining high-impact tasks.
- Add controlled replay workflows with explicit safety checks.
- Standardize incident diagnostics for retry storms and queue lag.

### Milestone C: Federation Stage 1 Pilot (Phase 7.4/7.5)
- Allowlisted inbound actor/object fetch and validation.
- Signed outbound delivery for selected object types.
- Retry/backoff/dead-letter behavior with operator replay guidance.

### Milestone D: Moderation Escalation + SLO Operations (Phase 7.3/7.6/7.7)
- Add escalation and SLA ownership flows for high/critical moderation queues.
- Define dashboard ownership and alert severity routing.
- Run failure drills and finalize beta readiness checklist.

## 6. Quality Gates

Before each release, run:

```bash
python manage.py check
python manage.py migrate --check
python manage.py test
```

And for deployment smoke checks:

```bash
curl http://localhost:8000/health/live/
curl http://localhost:8000/health/ready/
```

## 7. Notes on Tradeoffs

- Current notifications websocket consumer is intentionally a minimal scaffold.
- Federation tasks are placeholders by design; no fake ActivityPub claims.
- Server-rendered templates are intentionally simple to keep backend evolution fast.
