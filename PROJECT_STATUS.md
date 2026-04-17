# Freeparty Project Status

Last Updated: 2026-04-16 (Phase 6 complete, Phase 7 kickoff ready)

## Snapshot

Freeparty is a centralized-first, federation-ready Django social platform with working auth, actor profiles, posting, social interactions, moderation, notifications, timeline rendering, Docker operations, and major accessibility controls.

## Phase 6 Progress

- Mailcow SMTP baseline is in place with environment-driven settings, an SMTP connectivity/auth check command, and production notes for DNS and sender validation.
- Transactional account email now runs through Celery-backed SMTP tasks (verification, password-reset links, and system notices) with retry/backoff and sender-metadata validation coverage.
- High-frequency social actions now support async follow/unfollow and private follow-request approval flows without forcing full-page reloads.
- DM live updates now use deterministic cursor polling with backlog recovery and an optional feature-flagged websocket path, while retaining polling as fallback.
- Post sharing now supports outbound OpenGraph and Twitter card metadata, and inbound link unfurling with SSRF safeguards and preview-card rendering behind a feature flag.
- Inbox unification slice 3 enriches activity cards with source actor/post previews for notifications and latest-sender context for DM thread events.
- Device/key UX now includes explicit DM-side key inventory (server local/remote key lists, acknowledged key marker, browser-private-key status) with recovery guidance.
- Observability expansion now includes structured SMTP delivery attempt/failure/retry logs and structured async interaction/DM polling latency+failure metrics.

## Current Focus (Phase 7)

- Phase 7 roadmap is now authored in `phases_phase_7.md` with increments 7.0 through 7.7.
- Initial execution focus is PM security-gate closure, async dead-letter maturity, moderation escalation workflow, and federation allowlist pilot readiness.
- Operational readiness work is now centered on dashboard ownership, alert tuning, and failure drill playbooks before broader beta exposure.

## Runtime and Infrastructure

- Framework: Django 5.1
- Runtime: Daphne (ASGI)
- Database: PostgreSQL 16
- Cache/Broker: Redis 7
- Async workers: Celery worker + Celery beat
- Realtime scaffold: Django Channels notification websocket routing
- Local email testing: MailHog (`smtp://mailhog:1025`, UI at `http://localhost:8025`)
- Container orchestration: Docker Compose

Services in `compose.yaml`:

- `web`
- `db`
- `redis`
- `celery_worker`
- `celery_beat`
- `mailhog`

## Implemented Domain Features

### Accounts and Access

- Custom user model with username + email normalization
- Login, signup, logout, password reset flows
- Email verification flow + resend support
- Rate limiting on sensitive endpoints

### Actors and Profiles

- Public actor pages with profile metadata
- Avatar and profile editing
- Actor search (`/actors/search/`) for handles and matching posts
- Conditional relationship controls:
  - Follow / Unfollow
  - Block / Unblock
  - Report actor
- Profile privacy controls:
  - `show_follower_count`
  - `show_following_count`

### Posts and Engagement

- Post creation with visibility options
- Public and home timeline views
- Post detail pages
- Post actions:
  - Like toggle
  - Repost toggle
  - Share affordance
  - Report post
- Post ownership actions:
  - Edit post
  - Soft-delete post (`deleted_at`)
- Centralized policy checks now enforced for:
  - post view permissions (`can_view_post`)
  - post edit/delete ownership (`can_edit_post`, `can_delete_post`)
  - engagement permission checks on like/repost against visibility and block rules

### Comments

- Comment model and migration added
- Add comment to post detail
- Comment ownership actions:
  - Edit comment
  - Soft-delete comment (`deleted_at`)
- Comment rendering supports clickable mentions
- Centralized comment policy checks:
  - `can_comment_on_post`
  - `can_edit_comment`
  - `can_delete_comment`

### Permission and Ownership Layer (Phase 2 Priority A)

- Added reusable permission helpers in `apps/core/permissions.py`:
  - `can_view_post`
  - `can_edit_post`
  - `can_delete_post`
  - `can_comment_on_post`
  - `can_edit_comment`
  - `can_delete_comment`
  - `can_view_actor`
  - `can_follow_actor`
- Added post visibility selectors in `apps/posts/selectors.py` and adopted them in timeline services.
- Enforced blocked-relationship visibility in:
  - public timeline
  - home timeline
  - actor pages
  - search results
  - actor API listing
- API ownership enforcement added for post update/delete and follow creation.

### Pagination and Query Hygiene (Phase 2 Priority B)

- Added shared paginator helper: `apps/core/pagination.py`.
- Added reusable pagination UI partial: `templates/partials/pagination.html`.
- Added pagination to:
  - home timeline
  - public timeline
  - actor profile post list
  - search results (people and posts independently)
  - notifications list
- Added API-wide DRF page-number pagination defaults.
- Notifications list now supports lightweight unread/type filtering with paginated output.

### Privacy and Relationship Controls (Phase 2 Priority C)

- Added `Profile.is_private_account` with migration.
- Private account behavior implemented:
  - follow attempts create `pending` follow relations
  - account owner can approve/reject pending requests
  - private profiles are hidden from non-followers
  - private-account posts are hidden from non-followers (including public visibility posts)
- Added follow request queue UI:
  - `/social/follow-requests/`
  - approve/reject actions
- Added follow-request API actions:
  - `GET /api/v1/follows/incoming/`
  - `POST /api/v1/follows/{id}/approve/`
  - `POST /api/v1/follows/{id}/reject/`
- Added profile privacy API endpoint:
  - `GET/PATCH /api/v1/profiles/me/`

### Moderation Workflow (Phase 2 Priority D)

- Report statuses expanded to include:
  - `under_review`
  - `actioned`
  - legacy `reviewing` remains supported for compatibility
- Moderation dashboard upgraded with filter controls:
  - status
  - reason contains
  - reporter handle
  - target post id
  - date range (`from`/`to`)
  - target type (actor/post)
- Quick triage actions added from queue rows:
  - move to under_review
  - resolve
  - dismiss
- Report update behavior improved:
  - status updates consistently stamp `reviewed_by` and `reviewed_at`
  - creating moderation actions auto-sets report to `actioned` when status omitted
- Admin usability improved for reports/actions/notes with richer filters/search and ordering.

### Notifications and API Parity (Phase 2 Priority E/F slice)

- Notification dedupe helper added (`apps/notifications/services.py`) and used in follow/like/repost/comment pathways.
- Notification UI now supports single-item mark-read in addition to mark-all-read.
- Notification UI adds optional grouped display mode (group by day on current page).
- Notifications API endpoints added via `api/v1/notifications/`:
  - list (with filtering)
  - mark single read (`POST /api/v1/notifications/{id}/mark-read/`)
  - mark all read (`POST /api/v1/notifications/mark-all-read/`)
- Comment API parity added via `api/v1/comments/`:
  - create/edit/delete
  - owner-only edit/delete with centralized permission checks
  - soft-delete behavior on delete

### Phase 3 Kickoff: Reliability and Observability

- Added request observability middleware (`apps.core.middleware.RequestObservabilityMiddleware`):
  - propagates incoming `X-Request-ID` or generates one when absent
  - sets `X-Request-ID` response header for request correlation
  - logs `request_complete` entries with method/path/status/duration/request_id/user_id
  - logs `request_error` entries with request correlation context on exceptions
  - logs `slow_request` warnings when request latency exceeds threshold
- Added configurable threshold setting:
  - `REQUEST_SLOW_MS` (default `700`)
- Added middleware tests in `apps.core.tests`:
  - request-id generation
  - request-id passthrough
  - slow-request warning logging
  - request completion structured log coverage
  - request error structured log coverage
- Added shared Celery task observability helper (`apps.core.services.task_observability.observe_celery_task`) and instrumented tasks in:
  - `apps.accounts.tasks`
  - `apps.notifications.tasks`
  - `apps.federation.tasks`
- Added initial SLO baseline targets to operations runbook:
  - HTTP p95 latency
  - HTTP 5xx error rate
  - Celery queue lag
  - Celery task failure rate

### Phase 3.2 Kickoff: Moderation Staff API Parity (In Progress)

- Added staff-only moderation report API routes:
  - `GET /api/v1/moderation/reports/`
  - `GET /api/v1/moderation/reports/{id}/`
  - `POST /api/v1/moderation/reports/{id}/status/`
  - `POST /api/v1/moderation/reports/{id}/actions/`
  - `POST /api/v1/moderation/reports/{id}/notes/`
- Added moderation API serializers and filter parity for queue-like triage.
- Added moderation API tests for staff access, filters, status updates, action creation, and note creation.
- Added notification row context summaries (actor + source post + payload summary text) in HTML notification lists.

### Mentions

- `@handle` mention linkification in posts and comments via custom template filter

### Moderation and Notifications

- Report model usage for post and actor reports
- Notifications for follow/like/reply/mention/repost pathways (model + core paths wired)
- Notification list and mark-read baseline exists

### Phase 4.5 Kickoff: PM + E2E Foundation (Feature Flagged)

- Added new `apps.private_messages` domain app with foundational schema:
  - `Conversation`
  - `ConversationParticipant`
  - `UserIdentityKey`
  - `EncryptedMessageEnvelope`
- Added PM service interfaces with explicit feature gate:
  - `FEATURE_PM_E2E_ENABLED` (default `False`)
  - PM service operations raise when feature is disabled
- Added encrypted-envelope-only persistence path in service layer:
  - required fields: ciphertext, nonce, sender/recipient key ids
  - no plaintext message storage path introduced
- Added baseline PM foundation tests for:
  - feature-flag enforcement
  - encrypted envelope persistence
  - participant uniqueness constraints
- Added ADR and threat-model checklist for PM rollout gate:
  - `docs/adr/0001-pm-e2e-foundation.md`

### Phase 5 Kickoff: DM Initiation and Report Taxonomy Hardening

- Added user-facing DM initiation shell under feature flag:
  - `/messages/` conversation list
  - `/messages/start/{handle}/` direct conversation start action
  - `/messages/{id}/` conversation detail shell
- Added actor profile DM action with:
  - self-DM prevention
  - blocked-account prevention
  - direct conversation dedupe/reuse
- Added structured report intake flow:
  - dedicated report form page for actor/post targets
  - reason taxonomy (`dmca_ip`, `minor_safety`, `graphic_death_injury`, `non_consensual_intimate_media`, `impersonation`, `harassment`, `spam_scam`, `other`)
  - stored severity (`low`, `medium`, `high`, `critical`)
- Added tests for DM initiation HTML flow and report severity normalization/submission.

### Phase 5.2: Encrypted Envelope Compose/Store Flow

- Added encrypted envelope compose form on DM detail pages for direct conversations.
- Send flow derives active sender/recipient identity keys automatically for direct threads.
- DM HTML view continues to render metadata-only conversation rows; ciphertext is never rendered back to users.
- Added tests for:
  - blocked send state when active identity keys are missing
  - successful encrypted envelope storage when both participants have active keys

### Phase 5.5: Dev Ciphertext Preview Toggle

- Added optional DM detail ciphertext preview toggle for local debugging:
  - `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW=True`
  - requires `DEBUG=True` to render
- Default behavior remains metadata-only rendering with no ciphertext shown.
- Added PM HTML tests verifying ciphertext visibility when preview is enabled and hidden when disabled.

### Phase 5.6: Browser-Side Crypto Flow

- Added browser identity key registration endpoint:
  - `POST /messages/keys/register/`
  - server stores only public key, fingerprint, and key id; private key remains browser-local
- DM detail now supports:
  - plaintext compose with browser-side encryption before submit
  - client-side envelope decryption for rendering when required private key material exists
- Envelope persistence remains unchanged and server-side plaintext storage is still not introduced.
- Added PM tests for browser-key registration success and invalid payload handling.

### Phase 5.3: Key Change Warning and Acknowledgment

- Added participant-scoped remote key acknowledgment fields to DM conversations.
- DM detail now warns when the active remote identity key differs from the last acknowledged key.
- Added explicit acknowledgment action to confirm a newly verified remote key.
- Added tests for:
  - key-change detection contract
  - warning visibility for unacknowledged remote key changes
  - successful key acknowledgment flow

### Phase 5.3 Follow-up: Identity Key Bootstrap

- Added self-service identity key bootstrap endpoint for authenticated users:
  - `POST /messages/keys/bootstrap/`
- Messages list and DM detail now surface a "Generate my identity key" action when local key is missing.
- This removes shell/admin dependency for first-time encrypted DM onboarding in local environments.

### Phase 5.4: Moderation Queue Routing Improvements

- Added moderation dashboard filters for:
  - report reason category
  - report severity
- Added clearer report queue/detail display for reason/severity labels.
- Added staff API filtering parity for:
  - `severity`
  - `reason_category`
- Added tests for dashboard and API severity/category filtering behavior.

## Accessibility and UI Features

### Theme and Readability Controls

- Theme selector with multiple themes:
  - Auto
  - Light
  - Dark
  - Cyberpunk
  - Forest
  - Sunset
  - Ocean
  - Rose
- High contrast toggle
- OpenDyslexic font toggle
- Text size cycle (`normal`, `large`, `larger`)
- Spacing toggle (`normal`, `relaxed`)
- Reduced motion toggle (`normal`, `reduced`)
- Underline links toggle (`normal`, `underlined`)
- Preferences persisted in `localStorage`

### Keyboard and Navigation Support

- Skip link to main content
- Search shortcut: press `/` to focus header search
- Focus-visible outlines across interactive controls

### Reusable UI Components

- Shared post card partial used across timeline/explore/profile/search/detail contexts

## Operations and Tooling

- Start/stop helper scripts in `scripts/`
- Live service logs scripts (`logs.ps1` and `logs.cmd`)
- Static URL serving enabled in debug for admin/DRF assets

## Recent Changes Included in This Status

- Fixed base template corruption and duplicate block issue
- Added comments system + migrations
- Added actor and post search results page
- Added post/comment owner management actions (edit/delete)
- Added profile follower/following visibility controls + migration
- Added expanded accessibility preferences and toolbar controls
- Updated theme toolbar styling to avoid nested pill visual glitch
- Phase 2 increment started with centralized permission policy and blocked-relationship enforcement
- Added new permission-focused tests in `apps.posts.tests` and `apps.social.tests`
- Added pagination/filter tests in `apps.posts.tests` and `apps.notifications.tests`
- Added private-account visibility and follow-request tests in `apps.actors.tests`, `apps.posts.tests`, and `apps.social.tests`
- Added moderation workflow tests in `apps.moderation.tests`
- Added notification API/mark-read tests in `apps.notifications.tests`
- Added comment API parity tests in `apps.posts.tests`

## Data Model Additions Since Foundation

- `apps.posts.models.Comment`
- `apps.profiles.models.Profile.show_follower_count`
- `apps.profiles.models.Profile.show_following_count`
- `apps.posts.models.Comment`
- `apps.profiles.models.Profile.show_follower_count`
- `apps.profiles.models.Profile.show_following_count`
- `apps.moderation.models.TrustSignal` (Phase 3.3)
- `apps.moderation.models.SecurityAuditEvent` (Phase 3.3)
- `apps.core.models.AsyncTaskExecution` (Phase 3.4)
- `apps.core.models.AsyncTaskFailure` (Phase 3.4)

## Validation State

Latest checks run successfully:

- `python manage.py migrate`
- `python manage.py check`
- Template compile scan via Django loader (`TEMPLATE_ERRORS 0`)
- `python manage.py test apps.posts apps.social`
- `python manage.py test apps.posts apps.social apps.notifications`
- `python manage.py test apps.actors apps.posts apps.social apps.notifications`
- `python manage.py test apps.moderation apps.notifications apps.posts apps.social`
- `python manage.py migrate`
- `python manage.py check`
- Template compile scan via Django loader (`TEMPLATE_ERRORS 0`)
- `python manage.py test apps.posts apps.social`
- `python manage.py test apps.posts apps.social apps.notifications`
- `python manage.py test apps.actors apps.posts apps.social apps.notifications`
- `python manage.py test apps.moderation apps.notifications apps.posts apps.social`
- `python manage.py test apps.moderation apps.core apps.notifications` (Phase 3: 37 tests passing)
- `python manage.py test apps.actors apps.federation apps.core apps.moderation apps.notifications apps.accounts` (Phase 3.4 slice: 47 tests passing)

## Current Gaps / Next Recommended Milestones

1. Add API coverage for moderation queue/report actions (staff-only endpoints).
2. Add optional actor/post context summaries in notification rows to improve triage speed.
3. Expand integration tests for combined privacy+moderation+notification edge cases.
4. Continue Phase 3 hardening beyond kickoff (anti-abuse scoring, query profiling, reliability SLOs).

## Forward Roadmap Additions

- **Phase 4 candidate**: Media-first posting and timeline UX
  - complete image/video attachment posting flow (HTML + API)
  - media processing/validation hardening (mime/type/size/duration)
  - dedicated timeline tab/feed filter for photo/video posts only
  - media moderation and thumbnail pipeline test coverage
- **Future phase candidate**: Private messaging + E2E encryption
  - direct message domain and transport design
  - end-to-end encrypted message payload envelope and key lifecycle
  - local user-verification UX (fingerprint hex + generated visual identicon, similar in spirit to Telegram safety numbers)
  - device/session verification and key-change warnings
  - explicit threat model + crypto review gate before enabling by default

## Quick Command Reference

```bash
# Start stack
docker compose up --build

# Apply migrations
docker compose exec web python manage.py migrate

# Run checks
docker compose exec web python manage.py check

# Create admin user
docker compose exec web python manage.py createsuperuser

# View MailHog UI
# http://localhost:8025
```
