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

## 5. Suggested Next Milestones

### Milestone A: Stronger API Surface
- Add API serializers/views for moderation, notifications, and profiles.
- Add pagination and filtering strategy for timelines and posts.
- Add API permissions matrix (owner/mod/admin/public).

### Milestone B: Federation Stage 1
- Inbound fetch/parsing of remote actors to `FederationObject`.
- Outbound signed delivery worker built on `FederationDelivery`.
- Retry backoff + dead-letter queue behavior.

### Milestone C: Moderation Stage 1
- Moderator queue views and report triage workflow.
- Post visibility enforcement in query layer for hidden/taken_down.
- Moderator notes UI and action templates.

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
