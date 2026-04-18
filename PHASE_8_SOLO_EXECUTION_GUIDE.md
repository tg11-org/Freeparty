# Phase 8 Solo Execution Guide

Prepared: 2026-04-17
For: Solo builder workflow
Status: Ready to execute

## Why this exists

`phases_phase_8.md` describes the full hardening scope. This guide translates it into a realistic one-person plan with minimal context switching and low burnout risk.

## Solo operating rules

1. Work one increment at a time.
2. Prefer small, complete slices over broad partial progress.
3. Every session should end in one of two states:
- merged/committed working change, or
- clear rollback + notes of what was learned.
4. Never start a new increment while tests are failing from the current one.

## Priority split

Must-do now (highest risk reduction):
- 8.0 Production config guardrails
- 8.1 Security headers/cookie baseline
- 8.2 Hashtag indexing schema + parser integration
- 8.4 Async reliability expansion

Should-do next:
- 8.3 Hashtag backfill and query optimization verification
- 8.5 Abuse controls and moderation throughput

Can-wait if energy/time is low:
- 8.6 Backup/restore drill automation
- 8.7 Supply-chain/container posture closure

## Suggested weekly pace

Target: 6 to 8 weeks total, sustainable pace.

Week 1:
- Complete 8.0

Week 2:
- Complete 8.1

Week 3:
- Complete 8.2 (schema + parser + tests)

Week 4:
- Complete 8.3 (backfill + explain checks + rollout toggle)

Week 5:
- Complete 8.4

Week 6:
- Complete 8.5

Week 7:
- Complete 8.6

Week 8:
- Complete 8.7 and write closure report

If a week slips, do not stack new scope. Push the timeline and keep sequence.

## Session template (copy/paste)

Use this per work session:

1. Pick one small task from the current increment.
2. Implement only that task.
3. Run targeted tests for touched apps.
4. Update docs touched by behavior change.
5. Record short progress note in `PROJECT_STATUS.md`.
6. Stop.

## Increment-by-increment solo checklists

### Increment 8.0 - Production Config Guardrails

Definition of done:
- Custom Django deploy checks exist for critical env safety.
- Unsafe production combos fail with clear remediation text.
- Tests cover pass/fail guardrail paths.

Solo checklist:
- [ ] Add checks module and register checks.
- [ ] Fail on unsafe `DEBUG`, weak/empty `SECRET_KEY`, missing host/origin trust config.
- [ ] Add tests under core/settings checks area.
- [ ] Document required env keys in ops docs.

Rollback plan:
- Revert checks registration change and disable strict failure path if boot blocks unexpectedly.

### Increment 8.1 - Security Headers/Cookies

Definition of done:
- Production responses include required baseline headers.
- Cookie settings are hardened for production.
- CSP report-only has rollout path documented.

Solo checklist:
- [ ] Set/verify HSTS and secure cookie flags in production settings.
- [ ] Add `X-Content-Type-Options` and strict `Referrer-Policy` baseline.
- [ ] Add CSP report-only policy and documented enablement switch.
- [ ] Add endpoint header tests.

Rollback plan:
- Keep CSP in report-only and revert strict directives first if client regressions appear.

### Increment 8.2 - Hashtag Indexing Schema + Parser

Definition of done:
- Hashtags stored in normalized indexed tables.
- Post create/edit updates hashtag mappings idempotently.
- Multi-tag AND search path uses indexed relations.

Solo checklist:
- [ ] Add models + indexes + migration.
- [ ] Add parser service for extraction/normalization.
- [ ] Wire parser into post create/edit paths.
- [ ] Switch search query path to indexed relations behind a feature flag.
- [ ] Add parser and query tests.

Rollback plan:
- Toggle search back to legacy text-scan mode while keeping new tables dormant.

### Increment 8.3 - Backfill + Query Optimization

Definition of done:
- Existing posts have hashtag mappings.
- Query plans are acceptable for expected scale.
- Rollout toggle supports rapid fallback.

Solo checklist:
- [ ] Add management command for hashtag backfill.
- [ ] Capture query plan output before/after.
- [ ] Validate toggle behavior and fallback.
- [ ] Add runbook notes for backfill execution time and recovery.

Rollback plan:
- Disable indexed search flag and rerun with legacy path.

### Increment 8.4 - Async Reliability Expansion

Definition of done:
- Remaining critical tasks use reliability contracts.
- Replay limits and attribution are enforced.
- Tests cover duplicate suppression and failure recovery.

Solo checklist:
- [ ] Inventory remaining high-impact tasks.
- [ ] Wrap each with reliability lifecycle helpers.
- [ ] Add replay attribution fields + max replay guard.
- [ ] Add tests for retries/replays/idempotency.
- [ ] Update dead-letter triage runbook.

Rollback plan:
- Revert wrapper per-task if one integration causes regressions.

### Increment 8.5 - Abuse + Moderation Throughput

Definition of done:
- Adaptive throttles exist for abuse-prone actions.
- Moderation critical actions leave immutable audit trail.
- Queue visibility supports aging/SLA review.

Solo checklist:
- [ ] Add adaptive throttle policy for targeted action classes.
- [ ] Add immutable audit fields/logging for critical moderation transitions.
- [ ] Add queue filters/metrics for aging and ownership.
- [ ] Add enforcement and false-positive tests.

Rollback plan:
- Lower throttle strictness and keep audit logging enabled.

### Increment 8.6 - Backup/Restore Drills

Definition of done:
- Automated encrypted backup + retention configured.
- Scheduled restore drill validates integrity.
- Alerts fire on backup/restore failure.

Solo checklist:
- [ ] Implement backup automation script.
- [ ] Add restore rehearsal script/process.
- [ ] Add verification checks and failure alerts.
- [ ] Record measured RTO/RPO in operations docs.

Rollback plan:
- Keep manual backup as fallback while automation is corrected.

### Increment 8.7 - Supply Chain + Container Hardening

Definition of done:
- Dependency/image checks run in CI.
- Container runtime posture improved where compatible.
- Deployment gate enforces scan threshold.

Solo checklist:
- [ ] Add dependency CVE scan job.
- [ ] Add image scan job and threshold gate.
- [ ] Harden compose/runtime settings (non-root, capability drop, read-only where safe).
- [ ] Publish residual-risk register.

Rollback plan:
- Move failing gates to warning-only mode temporarily while remediating.

## Minimal command cadence per increment

Use these as your baseline command flow:

1. `python manage.py check --deploy`
2. `python manage.py test <touched_apps> --verbosity=1`
3. `python manage.py test` (full pass at increment completion)

## Burnout prevention mode

If you are tired:
- Do docs-only stabilization tasks.
- Avoid schema + infra changes in same session.
- Prefer one migration per session.
- End session after one green targeted test run.

## Definition of Phase 8 complete (solo)

All increments complete with:
- passing tests,
- deployment check pass in production-like config,
- updated docs,
- rollback notes,
- and one final closure summary with remaining risks.
