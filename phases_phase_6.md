Top-level objective:
Operationalize production email delivery via Mailcow and ship realtime UX foundations that remove full-page refresh friction while preserving safety and observability.

Context baseline entering Phase 6:
- Phase 5 delivered DM initiation, browser-side envelope encryption/decryption, fingerprint validation UX, and moderation severity routing.
- PM and crypto flows are still feature-gated and browser-private-key storage is device-local.
- Core interactions (likes/reposts/bookmarks and DM updates) now have async foundations but need full rollout and reliability polish.

Constraints:
- Do not weaken encrypted-envelope-only persistence guarantees.
- Keep Mailcow credentials and secrets environment-driven (never hard-coded).
- Add explicit fallback behavior for transient infra failures (SMTP outage, websocket disconnects).
- Preserve existing moderation and abuse controls while improving interactivity.

Work style requirements:
1. Ship in narrow increments with test coverage.
2. Keep production defaults safe; new behavior behind explicit feature flags where risk is non-trivial.
3. Update operations docs for every infrastructure-touching slice.
4. Include rollback notes for each increment.

Success criteria for Phase 6:
- Transactional email is delivered through Mailcow with verified DNS/auth and measurable reliability.
- DM and social interaction UX feels realtime/polished without page reload dependency.
- Device/key lifecycle UX for encrypted messaging is understandable and recoverable.
- Operators can observe and debug message/email flows with clear runbooks and telemetry.

PHASE 6 PART A - Mailcow Transactional Email Integration
Goal:
Move outbound transactional mail from console/dev behavior to production Mailcow delivery with robust operations support.

Requirements:
- Add environment settings for Mailcow SMTP host, port, auth, TLS, sender identity.
- Add health checks/diagnostics for SMTP connectivity and auth failures.
- Add retry policy and dead-letter visibility for failed sends.
- Document DNS/SPF/DKIM/DMARC prerequisites and rollout steps.

PHASE 6 PART B - Realtime Interaction UX
Goal:
Eliminate full-page refresh for high-frequency interactions and add near-realtime DM updates.

Requirements:
- Async like/repost/bookmark/follow request actions with optimistic UI states.
- DM auto-refresh or websocket push for new envelope arrival.
- Graceful fallback to non-JS and non-realtime behavior.
- Add test coverage for JSON/action contracts.

PHASE 6 PART C - Encrypted Messaging Device UX
Goal:
Reduce confusion and friction for multi-device key handling while preserving security model.

Requirements:
- Device-local key presence indicators and recovery actions.
- Clear key-rotation effects (who must re-verify, what old messages remain decryptable).
- Optional key backup/export strategy evaluation (security review required before shipping).

PHASE 6 PART D - Notification and Inbox Unification
Goal:
Provide a coherent user-facing inbox for social + DM activity.

Requirements:
- Add unread badges/live counters for notifications and DM threads.
- Add linkable activity feed items with context previews.
- Add pagination and filtering for high-volume users.

PHASE 6 PART E - Reliability and Observability Expansion
Goal:
Improve production diagnostics for email/DM/realtime paths.

Requirements:
- Structured logs for SMTP send attempts, failures, retry outcomes.
- Metrics for DM update latency, async interaction failure rates, polling/websocket fallback rates.
- Alert thresholds and runbook actions for incident response.

Execution plan by increments:

Increment 6.0
- Mailcow connectivity baseline.

Execution tasks (Increment 6.0):
- [ ] Add Mailcow SMTP env schema and secure defaults in settings.
- [ ] Add startup/management check command for SMTP connectivity and auth.
- [ ] Add docs for Mailcow DNS prerequisites (SPF, DKIM, DMARC, rDNS).

Increment 6.1
- Transactional email migration.

Execution tasks (Increment 6.1):
- [ ] Route verification/reset/system emails through Mailcow SMTP backend.
- [ ] Add retry/backoff behavior for transient SMTP failures.
- [ ] Add tests for failure + retry behavior and sender metadata correctness.

Increment 6.2
- Async interaction parity and optimistic UX.

Execution tasks (Increment 6.2):
- [ ] Expand no-refresh action handling to all high-frequency social actions.
- [ ] Add optimistic button state + rollback on API failure.
- [ ] Add tests for JSON response contracts and UI-state edge cases.

Increment 6.3
- DM live update hardening.

Execution tasks (Increment 6.3):
- [ ] Add robust polling/backoff strategy and duplicate-event protection.
- [ ] Evaluate websocket upgrade path for DM events (feature-flagged).
- [ ] Add tests for update cursor semantics and missed-message recovery.

Increment 6.4
- Device/key UX and support tooling.

Execution tasks (Increment 6.4):
- [ ] Add explicit device key inventory UI (current browser key vs server active key).
- [ ] Add user-facing guidance for recovery/rotation and verification steps.
- [ ] Add tests for missing-local-key and key-change warning flows.

Increment 6.5
- Inbox + notification unification.

Execution tasks (Increment 6.5):
- [ ] Add unified unread counters in top navigation.
- [ ] Add lightweight inbox dashboard linking DM threads and social notifications.
- [ ] Add pagination/filter tests for high-volume data paths.

Increment 6.6
- Observability + SLO rollout.

Execution tasks (Increment 6.6):
- [ ] Add structured logging for SMTP send/retry outcomes.
- [ ] Add DM and async interaction latency/failure metrics.
- [ ] Add alert/runbook updates in OPERATIONS.md with escalation guidance.

Acceptance gate per increment:
- manage.py check passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs and runbook updated for behavior/ops changes.

Documentation deliverables for Phase 6:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md

At end of Phase 6, provide:
1. Mailcow production-readiness summary (DNS/auth/delivery/retry posture)
2. Realtime UX completion summary (DM + social interactions)
3. Encrypted-device UX summary and remaining security review items
4. Reliability/SLO report and recommended Phase 7 scope
