Top-level objective:
Ship a production-ready hardening release that closes deployment misconfiguration risks, strengthens baseline web security posture, scales hashtag discovery/query paths, and improves operational recovery confidence.

Solo execution companion:
- See PHASE_8_SOLO_EXECUTION_GUIDE.md for one-person pacing, must-do vs can-wait priorities, and session-level execution flow.

Context baseline entering Phase 8:
- Phase 7 established PM security gate controls, key lifecycle protections, dead-letter foundations, and initial federation safety/reliability posture.
- Hashtag linkification and multi-hashtag search parsing now exist, but query execution still depends on text scans.
- Production safety relies on env correctness and runbook discipline; stronger automated guardrails are needed.
- Reliability observability exists, but restore drills and supply-chain enforcement are not yet fully operationalized.

Constraints:
- Preserve encrypted-envelope-only PM storage guarantees.
- Keep risky slices behind explicit feature flags when rollout blast radius is non-trivial.
- Prefer additive migrations and reversible rollout order.
- Keep centralized-first behavior stable while improving federation and async safety posture.

Work style requirements:
1. Ship in small, test-backed increments.
2. Include rollback notes for each increment.
3. Update OPERATIONS.md and implementation_reference.md for each infra/security-facing change.
4. Add system checks/automation before expanding runtime complexity.

Success criteria for Phase 8:
- Production startup fails fast on unsafe/missing security-critical config.
- Security headers/cookie posture reaches production baseline with test coverage.
- Hashtag search supports indexed multi-tag lookup without content-scan bottlenecks.
- Critical async paths have idempotency + dead-letter triage coverage.
- Backup/restore drills run on schedule and produce verifiable recovery evidence.
- Supply-chain and container hardening checks are enforced in CI/deploy process.

PHASE 8 PART A - Production Config Guardrails
Goal:
Prevent unsafe production deployments caused by configuration drift or omissions.

Requirements:
- Add deploy/system checks for critical production env requirements.
- Fail startup for unsafe defaults in production mode.
- Emit actionable check error messages for operators.
- Add tests for expected check failures and passing paths.

PHASE 8 PART B - Web Security Baseline Hardening
Goal:
Harden browser and cookie-layer protections with policy-tested defaults.

Requirements:
- Enforce strict transport/cookie/header settings for production.
- Introduce CSP rollout strategy (report-only first, then enforce).
- Add tests validating key security headers on representative endpoints.
- Document proxy/TLS prerequisites and common misconfiguration pitfalls.

PHASE 8 PART C - Hashtag Indexing and Search Scalability
Goal:
Move hashtag search from content scans to indexed query paths.

Requirements:
- Add normalized hashtag storage model(s) and post linkage.
- Parse hashtags on create/edit and maintain mappings idempotently.
- Support multi-hashtag AND query semantics via indexed joins.
- Add migration/backfill path and tests for parser edge cases.

PHASE 8 PART D - Async Reliability Expansion
Goal:
Apply reliability contracts consistently to remaining high-impact background flows.

Requirements:
- Expand idempotency/dead-letter coverage to notifications, media, federation, and email touchpoints not yet wrapped.
- Add replay safety constraints (max replay attempts, operator attribution, replay reason).
- Add tests for retry storms, duplicate suppression, and replay outcomes.
- Improve dead-letter triage ergonomics for ops workflows.

PHASE 8 PART E - Abuse Controls and Moderation Throughput
Goal:
Reduce abuse amplification and improve safety response speed.

Requirements:
- Add rate/velocity controls for abuse-prone actions with adaptive penalties.
- Add immutable audit context for moderation escalation/override paths.
- Add queue analytics for aging, ownership, and breach detection.
- Add tests for enforcement and false-positive-safe behavior.

PHASE 8 PART F - Backup/Restore Operational Readiness
Goal:
Make recovery verifiable, repeatable, and observable.

Requirements:
- Automate encrypted backup workflows with retention policy.
- Add scheduled restore drills and alerting on failure.
- Capture recovery-time evidence and include it in runbook process.
- Validate data integrity checks after restore.

PHASE 8 PART G - Supply Chain and Container Hardening
Goal:
Reduce package/image risk and tighten runtime container posture.

Requirements:
- Add dependency vulnerability scanning and version pinning checks in CI.
- Add base image refresh cadence and CVE gating.
- Run app/container as non-root where feasible and drop unnecessary capabilities.
- Add container-level healthcheck/readonly-fs policy where compatible.

Execution plan by increments:

Increment 8.0
- Production config guardrails and startup check contracts.

Execution tasks (Increment 8.0):
- [ ] Add custom Django deploy check module for critical env assertions.
- [ ] Fail for unsafe production combinations (DEBUG true, empty secret, missing host/origin trust config).
- [ ] Add explicit operator-facing remediation text.
- [ ] Add test coverage for failing and passing scenarios.

Increment 8.1
- Security headers and cookie posture baseline.

Execution tasks (Increment 8.1):
- [ ] Add/verify HSTS, secure cookies, content-type/referrer protections.
- [ ] Add CSP report-only policy with documented rollout switch.
- [ ] Add endpoint tests validating header presence/values.
- [ ] Update production proxy/TLS guidance in ops docs.

Increment 8.2
- Hashtag indexing schema + parser integration.

Execution tasks (Increment 8.2):
- [ ] Add Hashtag and post-link models/indexes.
- [ ] Add parser extraction on post create/edit with idempotent upsert behavior.
- [ ] Add multi-tag AND query path in search view/service.
- [ ] Add parser tests for #foo#bar, #woo #hoo, punctuation, and case normalization.

Increment 8.3
- Hashtag backfill + query optimization verification.

Execution tasks (Increment 8.3):
- [ ] Add management command to backfill hashtags for existing posts.
- [ ] Add explain/benchmark checks for query plan quality.
- [ ] Add rollout toggle to switch between legacy scan and indexed search path.
- [ ] Add rollback plan for parser/index regressions.

Increment 8.4
- Async reliability contract expansion.

Execution tasks (Increment 8.4):
- [ ] Apply reliability wrappers to remaining high-impact tasks.
- [ ] Add replay attribution fields and max replay guardrails.
- [ ] Add tests for duplicate deliveries and idempotency invariants.
- [ ] Document triage/replay decision flow in OPERATIONS.md.

Increment 8.5
- Abuse controls and moderation throughput hardening.

Execution tasks (Increment 8.5):
- [ ] Add adaptive throttling for abuse-prone action categories.
- [ ] Add moderation action audit immutability for critical transitions.
- [ ] Add moderation queue aging/SLA visibility endpoints or filters.
- [ ] Add tests for abuse-path enforcement and moderator override behavior.

Increment 8.6
- Backup/restore automation and drill workflow.

Execution tasks (Increment 8.6):
- [ ] Add backup automation script + retention controls.
- [ ] Add restore rehearsal workflow and verification checks.
- [ ] Add alert hooks for backup/restore job failures.
- [ ] Add runbook steps with expected RTO/RPO targets.

Increment 8.7
- Supply-chain and container posture closure.

Execution tasks (Increment 8.7):
- [ ] Add dependency and image vulnerability checks to CI.
- [ ] Harden compose/runtime container settings where compatible.
- [ ] Add deployment gate requiring clean security scan threshold.
- [ ] Produce Phase 8 closure report with residual-risk register.

Acceptance gate per increment:
- manage.py check --deploy passes in production-like config.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- OPERATIONS.md and implementation_reference.md updated for relevant behavior.
- Rollback notes included for migrations/feature flags/infra changes.

Documentation deliverables for Phase 8:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md
- docs/adr/ (when security architecture decisions change)

At end of Phase 8, provide:
1. Production configuration guardrail report (what is now blocked at startup and why).
2. Security header/cookie hardening report (before/after policy table).
3. Hashtag scalability report (parser/index migration + query performance impact).
4. Async reliability expansion report (idempotency/dead-letter/replay outcomes).
5. Backup/restore drill report (evidence, RTO/RPO, remediation backlog).
6. Supply-chain/container hardening report and Phase 9 recommendations.
