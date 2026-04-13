# Freeparty Project Status

Last Updated: 2026-04-12

## Snapshot

Freeparty is a centralized-first, federation-ready Django social platform with working auth, actor profiles, posting, social interactions, moderation, notifications, timeline rendering, Docker operations, and major accessibility controls.

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

### Comments

- Comment model and migration added
- Add comment to post detail
- Comment ownership actions:
  - Edit comment
  - Soft-delete comment (`deleted_at`)
- Comment rendering supports clickable mentions

### Mentions

- `@handle` mention linkification in posts and comments via custom template filter

### Moderation and Notifications

- Report model usage for post and actor reports
- Notifications for follow/like/reply/mention/repost pathways (model + core paths wired)
- Notification list and mark-read baseline exists

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

## Data Model Additions Since Foundation

- `apps.posts.models.Comment`
- `apps.profiles.models.Profile.show_follower_count`
- `apps.profiles.models.Profile.show_following_count`

## Validation State

Latest checks run successfully:

- `python manage.py migrate`
- `python manage.py check`
- Template compile scan via Django loader (`TEMPLATE_ERRORS 0`)

## Current Gaps / Next Recommended Milestones

1. Add dedicated permission helpers and tests for post/comment ownership rules.
2. Add pagination to search, actor post lists, and public timeline.
3. Add optional account-level privacy controls (private account approval flow).
4. Add stronger moderation workflows (review queues, action audit UX).
5. Add richer notifications UI (filters, grouped events).
6. Add API parity for new UI actions (comments, edits, deletes, privacy settings).
7. Expand automated tests across posts, comments, social actions, and template flows.
8. Add accessibility documentation and quick preset profiles.

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
