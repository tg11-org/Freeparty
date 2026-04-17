# Freeparty Social Media Foundation

Freeparty is a centralized-first, federation-ready social media foundation inspired by Twitter/Bluesky patterns. This repository is a production-minded Django base that supports immediate single-instance deployment while preserving schema and service seams for future federation.

## Architecture Summary

- Runtime stack: Django 5.1, PostgreSQL, Redis, Celery, Channels, Daphne.
- Deployment model: ASGI app (Daphne) behind reverse proxy (Apache assumed), with Celery worker/beat.
- Data model design: UUID primary keys and canonical URI fields for actors/posts/federation objects.
- Operational checks: liveness and readiness endpoints (`/health/live/`, `/health/ready/`).
- Domain split:
  - `apps.accounts`: custom user/authentication/email verification/rate-limited auth endpoints.
  - `apps.actors`: public identity layer (local + remote actor support).
  - `apps.profiles`: actor-facing profile metadata.
  - `apps.posts`: post + attachment models, soft-delete/moderation fields.
  - `apps.social`: follow/block/mute and engagement (like/repost/bookmark).
  - `apps.notifications`: typed notification records.
  - `apps.private_messages`: feature-flagged PM schema and encrypted envelope service seam.
  - `apps.moderation`: reports + moderation actions + moderator notes.
  - `apps.federation`: instance/object/delivery placeholders for future ActivityPub work.
  - `apps.timelines`: query-based timeline service + fanout-ready `TimelineEntry` placeholder.
  - `apps.core`: shared model mixins, URI helpers, and home timeline view.

## Key Foundation Features

- Custom user model from day one (`accounts.User`) with:
  - normalized unique email
  - unique validated lowercase username
  - account states: active, pending_verification, limited, suspended
  - email verification timestamp
- Actor abstraction decoupled from account login concerns.
- Canonical URI strategy (`SITE_URL`) for actor/post identity.
- Email verification flow using signed tokens + token persistence model.
- Password reset flow dispatched through Celery-backed SMTP tasks (with retry/backoff).
- Rate limiting on sensitive endpoints (signup, login, password reset, verify resend, posting, follow/unfollow).
- API-ready foundation via DRF routers (`/api/v1/...`).
- Channels websocket scaffolding for notifications (`/ws/notifications/`).
- Moderation and federation-first schemas included now, full protocols later.
- Notification UX includes bulk "mark all as read" action.
- Notification UX includes optional grouped view mode and single-item read actions.
- Media attachments are processed asynchronously with retry/backoff/idempotency tracking.
- Failed media processing jobs can be re-queued via `python manage.py reprocess_failed_media`.
- Staff media moderation API supports attachment state transitions (`normal`, `flagged`, `removed`) with visibility enforcement in post APIs.
- Staff navigation includes a quick link to Django Admin (`/admin/`).
- Phase 4.5 foundation adds feature-flagged PM models and encrypted-envelope-only service interfaces (disabled by default).
- Phase 5 kickoff adds feature-gated DM initiation HTML flows (`/messages/`, actor profile DM button, direct conversation reuse).
- Phase 5.2 adds encrypted-envelope compose/store flow in DM detail when both participants have active identity keys.
- Phase 5.3 adds key-change warning and acknowledgment flow when a participant's active remote identity key changes.
- Phase 5.3 follow-up adds UI identity-key bootstrap action (`/messages/keys/bootstrap/`) to unblock first-time encrypted DM setup.
- Phase 5.5 adds optional dev-only ciphertext preview in DM detail when `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=True` and `DEBUG=True`.
- Report intake now uses structured reason taxonomy with severity metadata and a dedicated report form.
- Phase 5.4 adds moderation queue routing controls for reason category + severity in dashboard/API triage workflows.
- Phase 5.6 adds browser-side crypto workflow in DM detail:
  - browser keypair generation + public-key registration (`POST /messages/keys/register/`)
  - plaintext encrypt-on-send in browser
  - decrypt-on-read when local private key is present on the device
- Phase 6 adds realtime and inbox UX foundations:
  - unified inbox route (`/inbox/`) with unread counters for notifications + DM threads
  - DM updates polling with cursor semantics and optional websocket live updates
  - async social action handling (follow/unfollow/like/repost/bookmark/follow-request actions)
- Phase 6 adds sharing improvements:
  - outbound OpenGraph/Twitter metadata for post detail embeds
  - inbound link unfurl previews behind `FEATURE_LINK_UNFURL_ENABLED` with SSRF safeguards
- Centralized object permission policy layer for post/comment/actor follow and visibility checks.
- Block-aware visibility enforcement in timeline and search queries.
- Optional private account mode with follow-request approval/rejection flow.
- API parity additions:
  - paginated list APIs by default
  - follow request incoming/approve/reject actions
  - profile privacy update endpoint (`/api/v1/profiles/me/`)
  - comments CRUD endpoint (`/api/v1/comments/`)
  - notifications read actions (`/api/v1/notifications/*`)
- Moderation queue workflow supports richer triage filters and quick status transitions.
- Phase 3 kickoff includes request correlation (`X-Request-ID`) and slow-request warning logs.
- Phase 3.1 adds structured request lifecycle logs (`request_complete`, `request_error`) and Celery task lifecycle logs (`task_start`, `task_success`, `task_failure`).
- Phase 3.2 kickoff adds staff moderation API routes under `/api/v1/moderation/reports/` for queue/detail/status/action/note workflows.

Implementation companion document:

- See `implementation_reference.md` for practical conventions and next milestones.
- See `OPERATIONS.md` for deployment/runtime runbook and incident triage.
- See `docs/adr/0001-pm-e2e-foundation.md` for PM/E2E foundation decisions and security review checklist.
- See `phases_phase_7.md` for full Phase 7 scope and increment breakdown.
- See `PHASE_7_KICKOFF.md` for a concise Phase 7 execution checklist.

## App Layout

```text
config/
  settings/
    base.py
    development.py
    production.py
  asgi.py
  wsgi.py
  urls.py
  api_urls.py
  celery.py
apps/
  accounts/
  actors/
  core/
  federation/
  moderation/
  notifications/
  private_messages/
  posts/
  profiles/
  social/
  timelines/
templates/
docker/
Dockerfile
compose.yaml
requirements.txt
.env.example
```

## Environment Configuration

Copy `.env.example` to `.env` and update values.

Required core settings:

- `DJANGO_SETTINGS_MODULE=config.settings.development` (or production)
- `SECRET_KEY`
- `DATABASE_URL` (PostgreSQL)
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `ALLOWED_HOSTS`
- `SITE_SCHEME`, `SITE_DOMAIN`
- `REQUEST_SLOW_MS` (optional, default `700`)
- `FEATURE_PM_E2E_ENABLED` (optional, default `False`; keep disabled until PM security gate sign-off)
- `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW` (optional, default `False`; only respected when `DEBUG=True`)
- `FEATURE_PM_WEBSOCKET_ENABLED` (optional, default `False`; enables DM websocket stream)
- `FEATURE_LINK_UNFURL_ENABLED` (optional, default `False`; enables asynchronous URL preview unfurl)

Browser E2E note:
- Browser private keys are stored client-side (localStorage) and are never uploaded to server.
- Losing browser storage for a key id means historical envelopes for that key id cannot be decrypted on that device.

Email:

- Development: `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`
- Production SMTP: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`

## Local Setup with Docker

1. Create env file:

```bash
cp .env.example .env
```

2. Start stack:

```bash
docker compose up --detach --build
```

If your environment uses legacy Compose, replace `docker compose` with `docker-compose`.

Ubuntu 22.04 note: `docker-compose` v1.29.x can fail during container recreate with
`KeyError: 'ContainerConfig'`. Prefer Docker Compose v2 plugin:

```bash
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
docker compose version
```

Windows helper scripts (non-destructive stop/start):

```powershell
./scripts/start.ps1
./scripts/stop.ps1
./scripts/logs.ps1              # View live logs from all services
./scripts/logs.ps1 web          # View logs from specific service (web, db, redis, etc.)
```

```cmd
scripts\start.cmd
scripts\stop.cmd
scripts\logs.cmd                REM View live logs from all services
scripts\logs.cmd web            REM View logs from specific service
```

These scripts intentionally use `docker compose stop` for shutdown, which preserves containers, volumes, and files. The `logs` scripts follow live output from all services (Ctrl+C to stop).

Linux server bootstrap (Ubuntu 22.04+):

```bash
chmod +x scripts/setup_server.sh
./scripts/setup_server.sh --site-domain freeparty.tg11.org --server-ip 127.5.0.0 --app-port 18000
```

If the target database already contains tables from a previous run, use:

```bash
./scripts/setup_server.sh --site-domain freeparty.tg11.org --server-ip 127.5.0.0 --app-port 18000 --reset-db
```

If you hit `PermissionError: [Errno 13] ... /app/staticfiles` on Linux bind mounts:

```bash
sudo ./scripts/fix_permissions.sh --path /var/www/Freeparty
```

What it does:

- creates `.env` from `.env.example` if missing
- switches to production settings (`DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG=False`)
- defaults `SITE_SCHEME=https`
- sets `BIND_IP`/`WEB_PORT` for Docker bind address and app port
- preserves existing custom infra port overrides in `.env` (`DB_PORT`, `REDIS_PORT`, `SMTP_PORT`, `MAILHOG_UI_PORT`), and only fills defaults if missing
- updates `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS`
- runs `docker compose up --detach --build`, `migrate --fake-initial`, and collectstatic
- static collection uses `collectstatic --clear` to replace stale or partial files from failed prior runs
- optional `--reset-db` does `down --volumes --remove-orphans` before startup (destructive for DB data)
- `scripts/fix_permissions.sh` can repair host ownership/permissions for bind-mounted runtime dirs (`staticfiles`, `media`)

Run Freeparty as a systemd service (recommended on servers):

```bash
sudo cp deploy/systemd/freeparty-compose.service /etc/systemd/system/freeparty-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now freeparty-compose.service
sudo systemctl status freeparty-compose.service
```

Service logs:

```bash
sudo journalctl -u freeparty-compose.service -f
docker compose logs --follow web
```

If Apache shows `502 Bad Gateway`, verify backend port alignment:

```bash
grep '^WEB_PORT=' .env
docker compose port web 8000
```

Your Apache proxy target (in `deploy/apache/freeparty.site.conf`) should match the published web port.

3. Create superuser (new shell):

```bash
docker compose exec web python manage.py createsuperuser
```

4. Access app:

- Web: `http://localhost:8000`
- Admin: `http://localhost:8000/admin/`

## Local Setup without Docker

1. Create and activate virtual environment.
2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Configure `.env` for local PostgreSQL + Redis.
4. Run migrations:

```bash
python manage.py migrate
```

5. Start Daphne:

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

6. Start Celery worker:

```bash
celery -A config worker -l info
```

7. Optional Celery beat:

```bash
celery -A config beat -l info
```

## How Redis and Postgres Are Used

- PostgreSQL:
  - primary relational data store for all domain models and constraints.
- Redis:
  - Django cache backend (`django-redis`)
  - rate limiting cache backend for `django-ratelimit`
  - Channels layer backend
  - Celery broker/result backend

## Security and Configuration Reminders

- Use `config.settings.production` in production.
- Keep `DEBUG=False` in production.
- Set secure cookies and HSTS (already in production settings).
- Configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `CORS_ALLOWED_ORIGINS` explicitly.
- Do not commit real `.env` secrets.
- Keep Apache proxy headers correct (`X-Forwarded-Proto`) for SSL-aware behavior.

## Anti-Abuse Strategy Notes

Current baseline:

- IP-aware rate limits for sensitive auth and action endpoints.
- User/IP limits for posting and follow/unfollow spam control.
- Account state machine for moderation actions (limited/suspended).
- Moderation-first report/action models to support enforcement.

Recommended future extensions:

- Add per-actor adaptive throttles and trust scoring.
- Introduce IP reputation and device/session fingerprint checks.
- Add async abuse pipelines via Celery tasks.

## Apache Reverse Proxy Deployment Notes

This app expects Apache to reverse proxy to Daphne.

- HTTP reverse proxy to Daphne upstream.
- WebSocket proxying should be enabled for `/ws/` endpoints when live notifications are enabled.
- Static/media can be served by Apache or moved to object storage/CDN.
- Preserve and trust proxy SSL header (`X-Forwarded-Proto`) only from trusted proxy networks.

Ready-to-use vhost template:

- `deploy/apache/freeparty.site.conf`

For your setup, this template terminates TLS on `https://freeparty.tg11.org`, redirects HTTP to HTTPS, and proxies:

- HTTP app traffic `/` -> `http://127.5.0.0:18000/`
- WebSocket traffic `/ws/` -> `ws://127.5.0.0:18000/ws/`
- Static/media are served by Apache directly from `/var/www/Freeparty/staticfiles` and `/var/www/Freeparty/media`

Install it on Ubuntu:

```bash
sudo a2enmod proxy proxy_http proxy_wstunnel headers rewrite ssl socache_shmcb
sudo cp deploy/apache/freeparty.site.conf /etc/apache2/sites-available/freeparty.conf
sudo a2ensite freeparty.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## Future Federation Roadmap

1. Implement ActivityPub actor/object fetch and signature verification.
2. Map `FederationObject` to local `Actor`/`Post` ingestion pipelines.
3. Build outbound signer + inbox/outbox delivery workers using `FederationDelivery`.
4. Add delivery retry backoff and dead-letter handling.
5. Enforce canonical URI-based dedup and conflict resolution.
6. Add shared inbox fanout and remote blocklist governance.

## Testing

Baseline tests included:

- user creation + normalization
- username validation
- email verification flow
- post creation + public view
- follow uniqueness and self-follow prevention constraints

Run tests:

```bash
python manage.py test apps.accounts apps.posts apps.social
```
