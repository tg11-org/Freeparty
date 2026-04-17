Top-level objective:
Ship a production-hardened public beta baseline by closing PM security gates, maturing reliability and safety operations, and delivering first real federation interoperability slices.

Context baseline entering Phase 7:
- Phase 6 delivered Mailcow-backed transactional email, async social interactions, DM live updates, inbox unification, richer embeds/unfurls, and expanded observability.
- Private messaging remains feature-gated with browser-local private keys and explicit key inventory/recovery UX.
- Structured logs and initial alert guidance exist, but dashboards/SLO enforcement and cross-service incident workflows still need operational maturity.
- Federation schemas and delivery scaffolding exist, but protocol interoperability is still placeholder-level.

Constraints:
- Do not weaken encrypted-envelope-only PM persistence guarantees.
- Preserve environment-driven secret handling (SMTP/federation signing keys/infra credentials).
- Keep high-risk rollouts behind explicit feature flags with safe production defaults.
- Preserve moderation and abuse controls while expanding automation.
- Keep backward compatibility for existing local-only deployments.

Work style requirements:
1. Ship in narrow increments with test coverage.
2. Add explicit rollback notes and feature-flag toggles for each risky slice.
3. Update operations/runbook docs for every infrastructure-touching change.
4. Prefer additive migrations and reversible rollout sequencing.

Success criteria for Phase 7:
- PM rollout gate is security-reviewed with clear operational safeguards.
- Async/realtime paths have production-grade retry/dead-letter/triage posture.
- Moderation safety operations support faster high-severity handling and auditability.
- Federation Stage 1 can interoperate with a limited allowlist of remote instances.
- Operators have actionable dashboards/alerts tied to practical runbooks.

PHASE 7 PART A - PM Security Gate Closure
Goal:
Complete security and trust hardening required for broader PM enablement.

Requirements:
- Finalize PM threat-model checklist and operational guardrails.
- Add server-enforced key registration/rotation policy boundaries.
- Add explicit user-facing safety messaging for key resets and trust continuity.
- Add staged rollout controls for PM feature enablement by environment/group.

PHASE 7 PART B - Async Reliability and Dead-Letter Maturity
Goal:
Move from retry-only behavior to full failure lifecycle visibility and controlled recovery.

Requirements:
- Extend task reliability contracts to high-impact async flows (email/unfurl/federation/notifications).
- Add dead-letter visibility and controlled replay workflows.
- Add idempotency and duplicate suppression where missing.
- Add incident-focused diagnostics for retry storms and prolonged lag.

PHASE 7 PART C - Moderation and Safety Escalation Workflow
Goal:
Improve high-severity moderation response speed and auditability.

Requirements:
- Add escalation policy hooks for critical reason categories.
- Add responder assignment/SLA timestamps for queue accountability.
- Add evidence-note consistency checks for legal/safety-sensitive reports.
- Add triage analytics views for backlog and turnaround health.

PHASE 7 PART D - Federation Stage 1 Interoperability
Goal:
Deliver initial real interoperability with remote instances behind strict controls.

Requirements:
- Inbound actor/object fetch + persistence for allowlisted instances.
- Outbound signed delivery for selected object types.
- Retry/backoff/dead-letter behavior for federation delivery failures.
- Instance-level controls (allowlist, blocklist, suspend/degrade policies).

PHASE 7 PART E - SLO Dashboards and Operational Readiness
Goal:
Convert logs/metrics into daily-operable signals and escalation practice.

Requirements:
- Define and instrument dashboard views for HTTP/task/SMTP/DM/social/federation paths.
- Add concrete alert thresholds with severity and ownership.
- Add failure drills and degraded-mode playbooks.
- Add release readiness checklist for beta promotion.

Execution plan by increments:

Increment 7.0
- PM security gate checklist closure and rollout controls.

Execution tasks (Increment 7.0):
- [ ] Convert PM ADR security checklist into a tracked completion matrix with owners.
- [ ] Add PM staged rollout toggle set (environment + cohort controls).
- [ ] Add tests for gate enforcement and disabled-state fallback behavior.
- [ ] Update runbook with PM rollback and incident containment steps.

Increment 7.1
- PM key lifecycle policy hardening.

Execution tasks (Increment 7.1):
- [ ] Add key-rotation cooldown/abuse protections and validation constraints.
- [ ] Add explicit trust-reset UX hooks when key continuity is broken.
- [ ] Add tests for invalid/abusive key registration and recovery flows.
- [ ] Document user support guidance for lost-device key scenarios.

Increment 7.2
- Async reliability/dead-letter standardization.

Execution tasks (Increment 7.2):
- [ ] Apply reliability wrappers to remaining high-impact tasks.
- [ ] Add dead-letter inspection + controlled replay management command(s).
- [ ] Add tests for idempotent retries and replay safety.
- [ ] Update operations docs with replay decision tree and safeguards.

Increment 7.3
- Moderation escalation and SLA instrumentation.

Execution tasks (Increment 7.3):
- [ ] Add escalation fields/workflow for high/critical reports.
- [ ] Add queue filtering by SLA breach/ownership state.
- [ ] Add tests for escalation transitions and audit stamping.
- [ ] Update moderator runbook with response-time expectations.

Increment 7.4
- Federation inbound allowlist pilot.

Execution tasks (Increment 7.4):
- [ ] Add allowlisted inbound actor/object fetch pipeline.
- [ ] Add validation/sanitization and storage contracts for remote data.
- [ ] Add tests for allowlist acceptance and blocked-instance rejection.
- [ ] Document onboarding checklist for pilot partner instances.

Increment 7.5
- Federation outbound signed delivery pilot.

Execution tasks (Increment 7.5):
- [ ] Implement signed outbound delivery for selected object actions.
- [ ] Add retry/backoff/dead-letter behavior for delivery failure classes.
- [ ] Add tests for signature generation/verification paths and failure recovery.
- [ ] Add operator docs for federation incident triage and replay.

Increment 7.6
- Observability dashboards and alert ownership.

Execution tasks (Increment 7.6):
- [ ] Publish dashboard definitions for HTTP/tasks/SMTP/DM/social/federation.
- [ ] Define alert severities, on-call ownership, and escalation chain.
- [ ] Add tests/checks for metric/log contract stability where feasible.
- [ ] Update OPERATIONS.md with dashboard-first triage workflow.

Increment 7.7
- Beta release hardening and failure drills.

Execution tasks (Increment 7.7):
- [ ] Run failure drills (SMTP outage, Redis lag, DM websocket disruption, federation retries).
- [ ] Capture degraded-mode behavior expectations and user-visible fallbacks.
- [ ] Add release checklist for schema/data/ops readiness.
- [ ] Produce go/no-go criteria for broader PM and federation exposure.

Acceptance gate per increment:
- `manage.py check` passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs/runbook updated for behavior and operations changes.
- Rollback notes included for any feature-flagged or migration-touching slice.

Documentation deliverables for Phase 7:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md
- docs/adr/ (when security/protocol decisions change)

At end of Phase 7, provide:
1. PM security gate closure report and rollout recommendation.
2. Async reliability/dead-letter maturity report with replay safety outcomes.
3. Moderation escalation/SLA performance summary.
4. Federation Stage 1 interoperability report (scope, limits, incident posture).
5. Beta readiness report and recommended Phase 8 scope.
