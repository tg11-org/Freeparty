# ADR 0002: Phase 7 Observability and Alert Ownership

## Status
Accepted

## Context
Phase 7 adds three new operational surfaces with different failure modes:
- replayable dead-letter failures
- moderator escalation and SLA handling
- federation pilot ingress/egress

Those flows are only useful in production if operators can detect ownership quickly and route incidents without ambiguity.

## Decision
Adopt the following alert ownership split:

- Platform:
  - HTTP 5xx rate > 1% for 10 minutes
  - SMTP delivery failure rate > 20% for 10 minutes
  - cache/database readiness failures
- Backend:
  - task terminal failure rate > 5% for 15 minutes
  - dead-letter replay volume spikes
  - DM polling latency p95 > 2s for 10 minutes
- Federation:
  - federation delivery backlog > 100 items for 15 minutes
  - signature validation failures from allowlisted partners
  - repeated 4xx delivery responses from one pilot partner
- Safety/Moderation:
  - critical moderation report unassigned for > 5 minutes
  - high/critical SLA breach counts above normal baseline

## Operational Queries
- Moderation escalation:
  - search for `incident_escalation`
- Dead-letter replay:
  - search for `manual_replay|max_retries_exceeded|task_failure`
- Federation pilot:
  - search for `apps.federation.tasks.execute_federation_delivery`

## Consequences
- Ops can distinguish platform issues from product-path issues faster.
- New alerts are tied directly to runbook actions in `OPERATIONS.md`.
- Federation rollout can stay disabled by default until operators accept the pilot thresholds.