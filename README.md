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
- Password reset flow integrated with Django email backend.
- Rate limiting on sensitive endpoints (signup, login, password reset, verify resend, posting, follow/unfollow).
- API-ready foundation via DRF routers (`/api/v1/...`).
- Channels websocket scaffolding for notifications (`/ws/notifications/`).
- Moderation and federation-first schemas included now, full protocols later.
- Notification UX includes bulk "mark all as read" action.
- Notification UX includes optional grouped view mode and single-item read actions.
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

What it does:

- creates `.env` from `.env.example` if missing
- switches to production settings (`DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG=False`)
- defaults `SITE_SCHEME=https`
- sets `BIND_IP`/`WEB_PORT` for Docker bind address and app port (plus default infra ports)
- updates `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS`
- runs `docker compose up --detach --build`, migrations, and collectstatic

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
