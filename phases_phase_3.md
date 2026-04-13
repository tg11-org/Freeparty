Top-level objective:
Move Freeparty from Phase 2 feature-complete foundation into Phase 3 production hardening: measurable reliability, anti-abuse resilience, operational observability, and stronger staff tooling while preserving current UX and architecture.

Context baseline (already in place):
- Core social features, privacy controls, moderation queue, notifications, and API parity for major user actions.
- Request correlation (`X-Request-ID`) and slow-request warning logs are implemented as kickoff.
- Dockerized runtime with Django + PostgreSQL + Redis + Celery + Channels + Daphne remains the deployment base.

Constraints:
- Keep Django + PostgreSQL + Redis + Celery + Channels + Daphne.
- Keep current multi-app architecture and service boundaries.
- Preserve federation-ready schemas and avoid fake federation claims.
- Prefer incremental, reversible changes over large rewrites.
- Avoid introducing heavyweight external infrastructure unless justified by clear value.
- Maintain Apache reverse-proxy compatibility assumptions.
- Preserve current accessibility controls and avoid UI regressions.

Work style requirements:
1. Start each increment with a short audit note:
   - objective
   - risk surface
   - touched apps
   - expected rollback path
2. Implement in small slices with explicit done criteria.
3. Add tests as part of each slice, not as a final pass.
4. Add instrumentation for behavior changes (logs/metrics/events) when practical.
5. Update docs (README / PROJECT_STATUS / implementation_reference / OPERATIONS) for every workflow change.

Success criteria for Phase 3:
- Reliability improves measurably (fewer unknown failures, faster diagnosis, safer retries).
- Abuse controls reduce spam/noise pathways without breaking normal user flows.
- Staff tools gain API support and auditable actions.
- Query performance remains stable under growth with fewer N+1 issues.
- Coverage expands for integration and failure-mode scenarios.
- Operations runbook supports real incident handling with concrete diagnostics.

PHASE 3 PART A - Observability and SLO Foundations
Goal:
Create actionable visibility into request, background task, and domain event health.

Requirements:
- Extend request observability beyond baseline:
  - structured request completion log format (method/path/status/duration/request_id/user_id when available)
  - error log correlation by request id
- Add Celery task observability:
  - task start/success/failure logs with task id and correlation metadata
  - standardized failure logging helper
- Define initial service-level objectives (SLOs):
  - request latency targets (p50/p95)
  - error rate target
  - queue lag/worker health target
- Add lightweight periodic health diagnostics endpoint or admin panel summary for staff/operators.

Deliverables:
- logging conventions documented
- SLO table documented in OPERATIONS
- tests for observability middleware/helpers

Done criteria:
- Every response carries correlation id.
- Exceptions in views and key tasks can be traced with shared identifiers.
- Operators can follow a runbook to diagnose high latency or elevated 5xx.

PHASE 3 PART B - Anti-Abuse and Trust Signals
Goal:
Reduce abuse/spam impact with practical, explainable controls.

Requirements:
- Add trust signal model/service (low complexity, extensible):
  - account age signal
  - email verification state
  - recent moderation reports/actions
  - action velocity (post/follow/like/repost bursts)
- Add adaptive throttling hooks for risky actions:
  - posting
  - follow requests
  - mentions/replies
  - report spam behavior
- Add temporary safety actions:
  - cooldown periods for repeated abuse triggers
  - optional soft limits before hard blocks
- Add moderation visibility:
  - show trust/signal summary on report detail and/or actor admin panel.

Deliverables:
- trust score/signal computation service
- abuse policy settings and thresholds in configuration
- tests for false-positive-sensitive paths

Done criteria:
- Suspicious burst patterns are slowed automatically.
- Staff can inspect why restrictions were applied.
- Legitimate normal usage remains unaffected in core tests.

PHASE 3 PART C - Performance and Query Profiling
Goal:
Improve throughput and consistency as data volume increases.

Requirements:
- Profile high-traffic pathways:
  - home timeline
  - public timeline
  - actor detail
  - notifications list
  - moderation dashboard
- Eliminate identified N+1 query patterns with select_related/prefetch_related/selectors.
- Add DB indexes where profiling proves value.
- Add query budget assertions to critical tests where practical.
- Define pagination defaults/maximums consistently for all relevant APIs.

Deliverables:
- profiling notes per endpoint
- selector/query updates with rationale
- migrations for new indexes (only when justified)

Done criteria:
- p95 query counts and endpoint latency improve or stay stable after changes.
- no major view endpoint regresses beyond agreed threshold.

PHASE 3 PART D - Reliability and Async Hardening
Goal:
Make async/event flows safe under retries, worker restarts, and transient failures.

Requirements:
- Add idempotency strategy for key async notifications/tasks.
- Standardize retry policy for Celery tasks:
  - bounded retries
  - exponential backoff
  - jitter where useful
- Add dead-letter or failure capture approach (table/log/event) for exhausted retries.
- Ensure critical state transitions are transactionally safe.
- Add integrity checks/management commands for periodic repair tasks.

Deliverables:
- task base helpers for retry/logging/idempotency
- operations runbook section for stuck/retrying tasks
- failure-path tests

Done criteria:
- duplicate task execution does not corrupt domain state.
- repeated transient failures are retried predictably and auditable.

PHASE 3 PART E - Moderation API and Staff Tooling Parity
Goal:
Complete staff workflow parity through secure, audited APIs.

Requirements:
- Add staff-only moderation API endpoints for:
  - report queue listing with filters
  - report detail
  - status transitions
  - action creation
  - moderator notes
- Enforce object-level staff permissions and audit metadata.
- Preserve HTML workflow parity with same business rules.
- Add robust API tests:
  - staff vs non-staff
  - invalid transitions
  - audit stamping consistency

Deliverables:
- moderation serializers/viewsets/API routes
- permission classes/policy helpers for moderation APIs
- updated API docs in README/implementation_reference

Done criteria:
- staff can execute full triage workflow via API safely.
- non-staff cannot read or mutate moderation resources.

PHASE 3 PART F - Notifications Quality and Delivery
Goal:
Increase clarity and correctness of notification experience under scale.

Requirements:
- Add optional actor/post context summaries in notification rows.
- Extend dedupe rules for noisy edge paths while preserving meaningful alerts.
- Add websocket delivery quality checks:
  - schema consistency
  - reconnect safety
  - no duplicate burst on reconnect
- Add read-state consistency checks across HTML and API under concurrent updates.

Deliverables:
- notification rendering/context enhancements
- delivery consistency tests (API + consumer-level)
- docs for notification event contract

Done criteria:
- notification stream remains informative without spam.
- HTML/API/websocket views converge on consistent read/unread state.

PHASE 3 PART G - Security Hardening and Auditability
Goal:
Reduce operational security risk and improve forensic visibility.

Requirements:
- Add security-sensitive event audit trail for:
  - login anomalies
  - password reset requests/completions
  - email verification events
  - moderator privilege actions
- Add proxy/trusted-header validation guidance and optional middleware checks.
- Review CSRF/CORS/secure-cookie settings across environments.
- Add account/session safety controls where low risk:
  - optional recent-login checks for sensitive account actions
  - optional suspicious session invalidation hooks.

Deliverables:
- audit event model/service (or equivalent log contract)
- security operations playbook updates
- tests for key audited events

Done criteria:
- security-sensitive flows produce searchable audit records.
- deployment guidance explicitly covers proxy/header trust pitfalls.

PHASE 3 PART H - Federation Readiness (No Full Protocol Rollout)
Goal:
Strengthen seams for future federation without claiming full ActivityPub support.

Requirements:
- Improve federation object lifecycle placeholders:
  - clearer object states
  - retry/error metadata
- Add signature/verification scaffolding interfaces (no full remote trust policy yet).
- Define outbound delivery contract and queue behavior.
- Add documented boundary between implemented vs planned federation features.

Deliverables:
- federation service interfaces and state docs
- tests for placeholder workflows

Done criteria:
- federation modules are cleaner and safer to extend in future phases.
- docs clearly state what is and is not supported.

PHASE 3 PART I - Integration and Regression Test Expansion
Goal:
Increase confidence in cross-domain behaviors and failure handling.

Requirements:
- Add integration tests spanning:
  - private account + follow request + timeline visibility
  - moderation action + notification side effects
  - block relationships across timeline/search/engagement APIs
  - read/write race-like scenarios for notification state
- Add smoke tests for operational commands/checks.
- Add targeted performance guard tests where practical.

Deliverables:
- cross-app integration test modules
- CI-friendly test grouping strategy

Done criteria:
- key multi-step flows are covered by deterministic tests.
- regressions in core safety rules are caught early.

Execution plan by increments:

Increment 3.1 (already started; complete and polish)
- Finalize observability baseline:
  - structured request completion logs
  - documented request id troubleshooting
- Validate and tune `REQUEST_SLOW_MS` defaults for local/dev/prod.

Execution tasks (Increment 3.1):
- [x] Add structured `request_complete` logs with:
  - [x] method
  - [x] path
  - [x] status
  - [x] duration_ms
  - [x] request_id
  - [x] user_id (when authenticated)
- [x] Add correlated `request_error` logs with request_id and context fields.
- [x] Add middleware tests for completion/error log coverage.
- [x] Add explicit SLO table to `OPERATIONS.md` (latency/error/queue baseline targets).
- [x] Add Celery task logging helper and initial task instrumentation.

Execution tasks (Increment 3.2 - in progress):
- [x] Add staff-only moderation report list/detail API endpoints.
- [x] Add moderation report filter parity in API (status/reason/actor/post/target/date range).
- [x] Add moderation status transition API action with audit stamping.
- [x] Add moderation action creation API action with `actioned` auto-state.
- [x] Add moderation note creation API action.
- [x] Add moderation API permission tests (staff vs non-staff).
- [x] Add notification actor/post context summaries in UI (Phase 3.2 remaining).

Increment 3.2
- Moderation API parity (Part E) + tests.
- Notification actor/post context summaries (Part F subset).

Execution tasks (Increment 3.4 - in progress):
- [x] Add idempotent task execution model (`AsyncTaskExecution`) with unique task_name/idempotency_key.
- [x] Add dead-letter style failure capture model (`AsyncTaskFailure`) for exhausted/transient task failures.
- [x] Add reliability helper service (`apps.core.services.task_reliability`) for start/success/failure lifecycle.
- [x] Integrate reliability helper into `execute_federation_delivery` task with idempotency key and execution recording.
- [x] Add federation reliability tests for successful execution and idempotent re-run behavior.
- [x] Standardize bounded retry/backoff/jitter policy across notification/accounts tasks.
- [x] Add management/operations workflow for reviewing terminal task failures.

Increment 3.3
- Anti-abuse trust signals and adaptive throttling (Part B).
- Initial security audit events (Part G subset).

Increment 3.3
- Anti-abuse trust signals and adaptive throttling (Part B).
- Initial security audit events (Part G subset).

Execution tasks (Increment 3.3 - complete):
- [x] Create TrustSignal model with account age, email verification, moderation history, and velocity signals.
- [x] Implement TrustSignalService to compute trust scores (0-100 scale) with configurable thresholds.
- [x] Implement ActionVelocityTracker for post/follow/like/repost burst detection.
- [x] Add adaptive throttling policy: score < 30 triggers throttling with reason and duration.
- [x] Create SecurityAuditEvent model for forensic audit trail logging.
- [x] Add SecurityAuditService with helpers for login success/failure, password reset, email verification, moderator actions.
- [x] Integrate security audit logging into accounts views (RateLimitedLoginView, password reset confirm, email verification).
- [x] Add trust signal summary field to moderation report detail API (target_actor_trust_signal).
- [x] Add comprehensive tests for trust signal computation, velocity anomaly detection, throttling policy.
- [x] Add tests for security audit event logging and retrieval.
- [x] Create migrations for TrustSignal and SecurityAuditEvent models.

Increment 3.5
- Query profiling + index/selector refinements (Part C).
- performance regression guard tests.

Increment 3.6
- Integration test expansion (Part I).
- final docs and release-readiness checklist.

Acceptance gate per increment:
- `python manage.py check` passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs updated for behavior and operations changes.
- Rollback note included for schema-affecting changes.

Documentation deliverables for Phase 3:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md

At end of Phase 3, provide:
1. Final audit summary (what improved, what remains)
2. Reliability and abuse-control outcomes
3. List of migrations added and why
4. List of tests added by app and scenario
5. Operational playbook delta and SLO adherence snapshot

Risk management and rollout notes:
- Prefer feature flags/settings toggles for new enforcement paths.
- Ship safety controls in monitor-only mode first when possible.
- Keep threshold values environment-driven.
- Include fallback behavior when Redis/Celery degraded.

Definition of done for full Phase 3:
- Staff API parity for moderation is complete and secured.
- Anti-abuse controls and observability are active, documented, and test-backed.
- Query and async reliability improvements are validated.
- Integration coverage substantially improved for cross-domain flows.
- Operators can diagnose and triage incidents with documented procedures.
