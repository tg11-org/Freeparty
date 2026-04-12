FYou are building the base for a new social media platform project called "Freeparty Social Media".

This is NOT a throwaway prototype. Build a clean, production-minded foundation that is centralized-first, but explicitly designed so federation can be added later without a full rewrite.

High-level concept:
- Freeparty Social Media is a Twitter/Bluesky-like social platform.
- Initial deployment is centralized on a single instance.
- The architecture and data model must be federation-ready from day one.
- The stack must use Django, PostgreSQL, Apache-compatible deployment, ASGI via Daphne, Redis, and Celery.
- The project should be easy to spin up locally or on a server using Docker / Docker Compose.
- The code should be organized cleanly for long-term development, not just “make it work”.

Core stack requirements:
- Python 3.12 preferred
- Django (latest stable suitable for production)
- PostgreSQL as the primary database
- Redis for cache, rate limiting support, Celery broker/backend support, and channels layer support
- Celery for background tasks
- Daphne for ASGI serving
- Django Channels enabled and wired correctly
- Docker and docker-compose / Compose support for local deployment
- Apache-compatible deployment assumptions:
  - app will sit behind Apache reverse proxy
  - support HTTP and future websocket proxying
- Use environment variables for secrets and config
- Include a .env.example file
- Include requirements and a clear README
- Use UUID-based primary/public identifiers where appropriate
- Use a custom Django user model from the start

Important architectural goals:
1. Centralized first
2. Federation-ready schema and services
3. Production-minded app structure
4. Strong auth/security basics
5. Moderate real-time support
6. Easy local setup with Docker
7. Clean, extensible code layout

Build a base project with these major app/model boundaries:

1) accounts
Purpose:
- authentication
- registration
- login
- logout
- password reset plumbing
- email verification
- future MFA compatibility
Requirements:
- custom user model
- UUID primary key or UUID public identifier
- unique username
- unique email
- normalized email handling
- username validation
- is_active / is_staff / is_superuser
- email_verified boolean or equivalent verified timestamp
- created_at / updated_at timestamps
- optional last_seen_at
- display_name optional
- support for future account states such as suspended, limited, pending_verification
- include model/service support for email verification tokens

2) identities or actors
Purpose:
- separate account login concerns from public social identity concerns
- future remote actor support
Requirements:
- Actor model or equivalent abstraction
- local and future remote actor distinction
- canonical public URI/identifier field
- username/handle representation rules
- link local actor to local account
- prepare structure for future remote actors:
  - remote domain / instance
  - inbox URL placeholder
  - outbox URL placeholder
  - shared inbox placeholder
  - remote actor JSON/document cache field optional
- actor status fields such as active, suspended, remote, deleted
- actor timestamps

3) profiles
Purpose:
- public-facing metadata separate from auth
Requirements:
- one-to-one or tightly linked with Actor
- bio
- avatar
- header/banner
- website URL
- location text
- birth date NOT required
- profile metadata timestamps
- future fields can be added later without messing up account/auth logic

4) posts
Purpose:
- core social post object
Requirements:
- UUID-based identity
- stable public/canonical ID or URI field
- author linked to Actor
- content text
- content warning / spoiler text field
- visibility enum:
  - public
  - unlisted
  - followers_only
  - private/direct-ready placeholder if needed
- in_reply_to self-reference
- thread root reference if useful
- quote/repost-ready structure, even if not fully implemented
- created_at / updated_at / deleted_at nullable
- soft delete support
- moderation state support
- local_only / federated-ready flags if useful
- do NOT hardcode everything around integer IDs

5) attachments
Purpose:
- media attached to posts
Requirements:
- image/video/file-ready model structure
- file path / storage support
- alt text
- mime type
- size
- processing status placeholder
- moderation/status flags
- created_at timestamps

6) social graph
Models/services:
- Follow
- Block
- Mute
Requirements:
- actor-to-actor relations
- unique constraints where appropriate
- follow state support:
  - pending
  - accepted
  - rejected
  - soft-removed if needed
- future private-account compatibility
- timestamps
- blocks should be enforceable in query/service layer
- muting should be distinct from blocking

7) engagement
Models/services:
- Like
- Repost or Boost
- Bookmark optional
Requirements:
- actor-linked
- target post-linked
- unique constraints
- timestamps
- designed cleanly enough to expand later

8) notifications
Purpose:
- notification records for local users
Requirements:
- support types such as follow, like, reply, mention, repost, verification, moderation/system notice
- actor recipient
- optional actor source
- optional post source
- read_at
- created_at
- design to support websocket delivery later

9) moderation
Models/services:
- Report
- ModerationAction
- maybe ModerationNote/admin note
Requirements:
- reports against actor and/or post
- reason/category
- freeform description
- reporter actor/account
- status fields
- review timestamps
- moderator relation if useful
- room for account suspension / post takedown / visibility limitation

10) federation-ready base
Even if federation is NOT implemented now, the schema and service layer must prepare for it.
Create baseline models such as:
- Instance
- RemoteObject or FederationObject
- DeliveryAttempt / FederationDelivery
Requirements:
- remote instance/domain tracking
- actor/post canonical URI fields
- dedup-friendly external identifier handling
- placeholder fields for signed delivery metadata / fetch timestamps / processing state
- delivery retry state placeholders
- do NOT fully implement ActivityPub unless necessary, but the structure should clearly support future federation

11) timelines
Purpose:
- support future home/public timelines
Requirements:
- create a timeline service module, even if simple
- keep feed logic OUT of views as much as possible
- if useful, create placeholder TimelineEntry model for future fanout-on-write
- for now, a simple query-based timeline is acceptable, but structure the code so it can evolve later

Technical requirements:
- Use Django settings split by environment:
  - base.py
  - development.py
  - production.py
- Config from environment variables
- Use sensible packages for:
  - PostgreSQL driver
  - Celery
  - Redis
  - image/file handling if needed
  - email verification flow
  - rate limiting
- Keep dependencies reasonable and production-appropriate
- Include typing where practical
- Keep code style consistent and maintainable

Authentication and verification requirements:
- registration flow
- login flow
- logout flow
- email verification flow
- resend verification flow
- password reset flow
- verified-email requirement toggle for core actions like posting, configurable in settings
- use signed tokens or similarly safe approach
- do NOT fake verification; wire actual Django email backend integration
- support dev console email backend and SMTP config for production

Rate limiting and abuse prevention:
- add rate limiting for sensitive endpoints:
  - login
  - signup
  - password reset request
  - email verification resend
  - posting
  - follow/unfollow spam
- rate limiting should be Redis-backed if practical
- include anti-abuse design notes in README
- include basic account/IP-aware throttling strategy
- make it easy to extend later
- if using Django REST Framework for APIs, apply throttling there as well if relevant

Security requirements:
- secure password hashing with Django defaults
- CSRF protection enabled where appropriate
- secure cookie settings configurable for production
- basic security settings for production included
- host/origin/cors configuration patterns documented
- no hardcoded secrets
- no debug-only shortcuts in production config
- soft-delete and moderation-friendly data handling where applicable

API and app structure:
Build both:
1. server-renderable Django foundation
2. API-ready foundation

It is acceptable to provide:
- Django templates for auth/basic pages
- DRF-based API endpoints for core resources
But the key is to leave the project ready for either:
- template-driven frontend
- HTMX frontend
- SPA/mobile client later

Recommended project layout:
- config/ for settings, ASGI, WSGI, Celery, URLs
- apps/
  - accounts/
  - actors/ or identities/
  - profiles/
  - posts/
  - social/
  - notifications/
  - moderation/
  - federation/
  - core/
- templates/
- static/
- media/
- docker/
- scripts/

ASGI / WSGI requirements:
- configure ASGI correctly for Django + Channels + Daphne
- keep WSGI present for compatibility where useful
- include working asgi.py
- include daphne command/config guidance
- Redis channels layer config should be included
- websocket plumbing may be minimal, but the base should support future live notifications

Celery requirements:
- working Celery app configuration
- Redis broker/backend
- example tasks:
  - send verification email
  - send password reset email or notification
  - process notification fanout placeholder
  - federation delivery placeholder
- ensure tasks auto-discover properly
- include startup commands in README and docker-compose

Docker requirements:
Provide Docker support that lets another developer run the project with minimal hassle.
Include:
- Dockerfile for Django app
- docker-compose.yml or compose.yaml with services for:
  - web/app
  - postgres
  - redis
  - celery worker
  - optionally celery beat
- volumes where appropriate
- startup command or entrypoint that can run migrations and start Daphne
- developer-friendly defaults
- .env.example
- documented first-run commands
- avoid overly magical scripts unless they are clearly documented

Database requirements:
- PostgreSQL only, not SQLite as the main path
- UUID-friendly schema
- proper constraints and indexes
- unique indexes for usernames/emails/relationships where needed
- migration files included
- timestamps and ordering choices sensible
- use database integrity constraints, not just application checks

Username / handle rules:
- usernames must be unique
- validate allowed characters cleanly
- case normalization strategy should be explicit
- reserve room for future federated handles like user@domain even if local usernames are just user
- do not tie public identity only to database PK

Canonical IDs / URIs:
- posts and actors should have stable canonical public identifiers or at least fields ready for them
- prepare helper methods/services that can generate canonical URLs from settings/domain
- design with future federation object references in mind

Admin and moderation tooling:
- register important models in Django admin
- make admin useful, not bare minimum
- include list filters/search where sensible
- make it easier to inspect:
  - users
  - actors
  - posts
  - reports
  - follows
  - notifications
  - federation placeholders

Initial feature scope:
Implement a functional base, not every feature in existence.
Required base functionality:
- signup
- login/logout
- email verification
- profile creation/editing
- create post
- list posts
- view user/actor profile
- follow/unfollow
- basic home/public timeline
- basic notifications record creation
- report post/account base
- admin access
Optional but nice if time allows:
- likes
- reposts
- websocket notifications placeholder
- bookmark skeleton
- basic search placeholder

Code quality expectations:
- no giant god files
- service layer or selectors/helpers where appropriate
- serializers/forms/views separated cleanly
- comments only where useful
- README explains architecture
- avoid overengineering, but do not make a toy app
- migrations should run cleanly
- app should boot cleanly with Docker

Testing:
Provide at least a minimal test base for:
- user creation
- username validation
- email verification flow
- post creation
- follow constraint logic
- one or two API or view tests
Not exhaustive, but enough to prove the base works

README requirements:
The README should include:
- project overview
- architecture summary
- app layout
- local setup using Docker
- environment variable documentation
- how to run migrations
- how to create a superuser
- how to run Daphne
- how to run Celery worker
- how Redis/Postgres are used
- notes about Apache reverse proxy deployment
- notes about future federation direction
- security/configuration reminders

Apache deployment notes:
Do not configure Apache itself inside the app, but document deployment assumptions:
- Apache will reverse proxy to Daphne
- websocket proxying may be needed later
- static/media can be served by Apache or external storage/CDN
- app should trust proxy headers safely when configured
- mention secure proxy SSL header handling expectations

Deliverables:
1. Full Django project scaffold with apps and settings
2. Dockerized local environment
3. PostgreSQL/Redis/Celery/Daphne wired together
4. Custom user model and core social models
5. Email verification and auth flows
6. Basic rate limiting and abuse protection foundation
7. Admin integration
8. README with setup and architecture notes
9. Clean migrations
10. A short section called “Future Federation Roadmap” in the README

Implementation style:
- Prefer correctness, cleanliness, and extensibility
- Make reasonable decisions without blocking on every tiny ambiguity
- Use best-practice Django patterns where practical
- If something is left as a placeholder, make that explicit in code comments and README
- Do not leave fake stubs pretending to be complete features

At the end, provide:
- a short architecture summary
- a tree of the created files/folders
- setup instructions
- any assumptions or tradeoffs made

notes:
Design the identity and object layers so that future support for decentralized identities, remote actors, signed object delivery, and canonical URI-based references is straightforward, even if the initial implementation remains centralized.
Treat moderation as a first-class concern. Build models and admin tooling assuming the platform will eventually need account suspension, post takedowns, shadow/limited visibility states, user reporting, and internal moderator notes.