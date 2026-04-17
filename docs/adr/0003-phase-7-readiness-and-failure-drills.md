# ADR 0003: Phase 7 Readiness and Failure Drills

## Status
Accepted

## Context
Phase 7 introduces retry/replay tooling, critical moderation escalation, and signed federation pilot delivery. Those changes are safe only if operators practice degraded-mode behavior before broader rollout.

## Decision
Run and record the following drills before widening rollout beyond internal/beta cohorts:

1. Redis unavailable
2. SMTP relay unavailable
3. Database latency or readiness failure
4. DM websocket disruption or PM rollback
5. Federation outbound failure storm

Each drill record must capture:
- time to detection
- operator action taken
- rollback or degraded-mode decision
- user-visible impact
- runbook corrections identified during the drill

## Go/No-Go Criteria
- Dead-letter replay command exercised successfully on a non-production-safe payload
- Critical moderation escalation logs observed end-to-end
- Federation outbound remains behind `FEATURE_FEDERATION_OUTBOUND_ENABLED` until shared secret and partner inbox are verified
- Rollback steps validated for PM and federation flags
- On-call ownership acknowledged by Platform, Backend, and Federation owners

## Consequences
- Rollout decisions are based on practiced operational behavior rather than feature completeness alone.
- Phase 7 remains reversible at each flag boundary.