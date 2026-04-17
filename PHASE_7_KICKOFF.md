# Phase 7 Kickoff Checklist

This checklist translates `phases_phase_7.md` into practical first-sprint execution steps.

## Scope

Primary goal: start Phase 7 with the highest-risk controls first (PM gate, async reliability, and operational readiness), while keeping all risky features safely gated.

## Week 1 Priorities

- [ ] Confirm PM rollout defaults remain safe in target environments:
  - `FEATURE_PM_E2E_ENABLED=False` unless explicitly approved
  - `FEATURE_PM_WEBSOCKET_ENABLED=False` until websocket drills complete
  - `FEATURE_LINK_UNFURL_ENABLED=False` until fetch policy validation is complete
- [ ] Convert PM ADR checklist into owner-assigned tracking items.
- [ ] Define incident rollback triggers for each Phase 7.0/7.1 change.
- [ ] Validate SMTP + interaction telemetry queries in `LOGS_SETUP.md` against real logs.

## Week 2 Priorities

- [ ] Implement and test PM gate enforcement paths (enabled/disabled cohort behavior).
- [ ] Implement key-rotation abuse protections and validation constraints.
- [ ] Add/extend tests for key lifecycle edge cases and trust-reset messaging.
- [ ] Document user-support playbook for lost-device private keys.

## Week 3 Priorities

- [ ] Apply reliability wrappers to remaining high-impact Celery flows.
- [ ] Add dead-letter inspection and controlled replay command workflows.
- [ ] Add replay/idempotency tests for newly covered tasks.
- [ ] Add operations decision tree for replay safety.

## Definition of Ready (Per Increment)

- [ ] A feature flag or rollback path exists for risky behavior changes.
- [ ] Tests cover success and failure-path behavior.
- [ ] `manage.py check` passes.
- [ ] Touched docs are updated (`README.md`, `OPERATIONS.md`, `PROJECT_STATUS.md`, `implementation_reference.md`).

## Definition of Done (Phase 7 Entry Complete)

- [ ] Increment 7.0 and 7.1 implementation plans are approved.
- [ ] Alert ownership and escalation contacts are identified for 7.2+.
- [ ] Federation allowlist pilot prerequisites are documented.
- [ ] First failure drill schedule is agreed.

## Companion Docs

- Full roadmap: `phases_phase_7.md`
- Operations runbook: `OPERATIONS.md`
- Logging/telemetry guide: `LOGS_SETUP.md`
- PM foundation ADR: `docs/adr/0001-pm-e2e-foundation.md`
