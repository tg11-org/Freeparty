Top-level objective:
Operationalize production email delivery via Mailcow and ship realtime UX foundations that remove full-page refresh friction while preserving safety and observability.

Context baseline entering Phase 6:
- Phase 5 delivered DM initiation, browser-side envelope encryption/decryption, fingerprint validation UX, and moderation severity routing.
- PM and crypto flows are still feature-gated and browser-private-key storage is device-local.
- Core interactions (likes/reposts/bookmarks and DM updates) now have async foundations but need full rollout and reliability polish.

Constraints:
- Do not weaken encrypted-envelope-only persistence guarantees.
- Keep Mailcow credentials and secrets environment-driven (never hard-coded).
- Add explicit fallback behavior for transient infra failures (SMTP outage, websocket disconnects).
- Preserve existing moderation and abuse controls while improving interactivity.

Work style requirements:
1. Ship in narrow increments with test coverage.
2. Keep production defaults safe; new behavior behind explicit feature flags where risk is non-trivial.
3. Update operations docs for every infrastructure-touching slice.
4. Include rollback notes for each increment.

Success criteria for Phase 6:
- Transactional email is delivered through Mailcow with verified DNS/auth and measurable reliability.
- DM and social interaction UX feels realtime/polished without page reload dependency.
- Device/key lifecycle UX for encrypted messaging is understandable and recoverable.
- Operators can observe and debug message/email flows with clear runbooks and telemetry.

PHASE 6 PART A - Mailcow Transactional Email Integration
Goal:
Move outbound transactional mail from console/dev behavior to production Mailcow delivery with robust operations support.

Requirements:
- Add environment settings for Mailcow SMTP host, port, auth, TLS, sender identity.
- Add health checks/diagnostics for SMTP connectivity and auth failures.
- Add retry policy and dead-letter visibility for failed sends.
- Document DNS/SPF/DKIM/DMARC prerequisites and rollout steps.

PHASE 6 PART B - Realtime Interaction UX
Goal:
Eliminate full-page refresh for high-frequency interactions and add near-realtime DM updates.

Requirements:
- Async like/repost/bookmark/follow request actions with optimistic UI states.
- DM auto-refresh or websocket push for new envelope arrival.
- Graceful fallback to non-JS and non-realtime behavior.
- Add test coverage for JSON/action contracts.

PHASE 6 PART C - Encrypted Messaging Device UX
Goal:
Reduce confusion and friction for multi-device key handling while preserving security model.

Requirements:
- Device-local key presence indicators and recovery actions.
- Clear key-rotation effects (who must re-verify, what old messages remain decryptable).
- Optional key backup/export strategy evaluation (security review required before shipping).

PHASE 6 PART D - Notification and Inbox Unification
Goal:
Provide a coherent user-facing inbox for social + DM activity.

Requirements:
- Add unread badges/live counters for notifications and DM threads.
- Add linkable activity feed items with context previews.
- Add pagination and filtering for high-volume users.

PHASE 6 PART E - Reliability and Observability Expansion
Goal:
Improve production diagnostics for email/DM/realtime paths.

Requirements:
- Structured logs for SMTP send attempts, failures, retry outcomes.
- Metrics for DM update latency, async interaction failure rates, polling/websocket fallback rates.
- Alert thresholds and runbook actions for incident response.

PHASE 6 PART F - Rich Link Embeds (Outbound OG + Inbound Unfurl)
Goal:
Make posts look great when shared to external platforms and automatically render link previews when posts contain URLs.

Requirements (outbound — Freeparty posts shared to Discord/Twitter/etc.):
- Add OpenGraph and Twitter Card meta tags to post detail pages.
- Include: og:title, og:description, og:image (first attachment or avatar), og:url, og:type.
- Add Twitter-specific: twitter:card, twitter:title, twitter:description, twitter:image.
- Keep sensitive/NSFW/private posts from generating rich embeds (serve minimal meta or 404 for private-account posts).

Requirements (inbound — links inside post content render as preview cards):
- When a post body contains a URL, fetch and store unfurl metadata (title, description, thumbnail, domain) server-side via Celery task.
- Store metadata in a dedicated LinkPreview model (url, title, description, thumbnail_url, fetched_at).
- Render a preview card beneath post content in post_card.html.
- Support rich embeds for YouTube (use oEmbed / noembed.com) to show video title, thumbnail, channel.
- Rate-limit and sandbox outbound HTTP fetches; disallow SSRF targets (private IP ranges, metadata endpoints).
- Feature-flag: FEATURE_LINK_UNFURL_ENABLED (default False in dev; operators opt-in).

Execution tasks (Increment 6.7 — Outbound OG meta):
- [ ] Add OG + Twitter Card meta block to post detail template.
- [ ] Guard: skip rich OG for private/NSFW posts (serve safe fallback meta only).
- [ ] Add tests verifying meta tag presence/absence based on post state.

Execution tasks (Increment 6.8 — Inbound link unfurl):
- [ ] Add LinkPreview model + migration.
- [ ] Add async Celery task: fetch URL, parse OG/oEmbed, store LinkPreview; skip SSRF targets.
- [ ] Wire task to post-save signal (only when body URL detected and flag enabled).
- [ ] Render preview card in post_card.html when LinkPreview exists for post.
- [ ] Add tests for SSRF guard, task idempotency, and card render toggle.



Increment 6.0
- Mailcow connectivity baseline.

Execution tasks (Increment 6.0):
- [x] Add Mailcow SMTP env schema and secure defaults in settings.
- [x] Add startup/management check command for SMTP connectivity and auth.
- [x] Add docs for Mailcow DNS prerequisites (SPF, DKIM, DMARC, rDNS).

Increment 6.1
- Transactional email migration.

Execution tasks (Increment 6.1):
- [x] Route verification/reset/system emails through Mailcow SMTP backend.
- [x] Add retry/backoff behavior for transient SMTP failures.
- [x] Add tests for failure + retry behavior and sender metadata correctness.

Increment 6.2
- Async interaction parity and optimistic UX.

Execution tasks (Increment 6.2):
- [x] Expand no-refresh action handling to all high-frequency social actions.
- [x] Add optimistic button state + rollback on API failure.
- [x] Add tests for JSON response contracts and UI-state edge cases.

Increment 6.3
- DM live update hardening.

Execution tasks (Increment 6.3):
- [x] Add robust polling/backoff strategy and duplicate-event protection.
- [x] Evaluate websocket upgrade path for DM events (feature-flagged).
- [x] Add tests for update cursor semantics and missed-message recovery.

Increment 6.4
- Device/key UX and support tooling.

Execution tasks (Increment 6.4):
- [x] Add explicit device key inventory UI (current browser key vs server active key).
- [x] Add user-facing guidance for recovery/rotation and verification steps.
- [x] Add tests for missing-local-key and key-change warning flows.

Increment 6.5
- Inbox + notification unification.
- Status: Complete (slice 3 delivered: richer activity-card context previews for source actor/post and latest DM sender).

Execution tasks (Increment 6.5):
- [x] Add unified unread counters in top navigation.
- [x] Add lightweight inbox dashboard linking DM threads and social notifications.
- [x] Add pagination/filter tests for high-volume data paths.

Increment 6.6
- Observability + SLO rollout.

Execution tasks (Increment 6.6):
- [x] Add structured logging for SMTP send/retry outcomes.
- [x] Add DM and async interaction latency/failure metrics.
- [x] Add alert/runbook updates in OPERATIONS.md with escalation guidance.

Increment 6.7
- Outbound OG meta tags for Discord/Twitter/Facebook embeds.

Execution tasks (Increment 6.7):
- [x] Add OG + Twitter Card meta block to post detail template.
- [x] Guard: skip rich OG for private/NSFW posts.
- [x] Add tests verifying meta presence/absence.

Increment 6.8
- Inbound link unfurl / preview cards.

Execution tasks (Increment 6.8):
- [x] Add LinkPreview model + migration.
- [x] Add SSRF-safe Celery unfurl task (OG + YouTube oEmbed).
- [x] Wire task to post-save signal behind FEATURE_LINK_UNFURL_ENABLED flag.
- [x] Render preview card in post_card.html.
- [x] Add tests for SSRF guard, idempotency, card toggle.

Acceptance gate per increment:
- manage.py check passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs and runbook updated for behavior/ops changes.

Documentation deliverables for Phase 6:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md

At end of Phase 6, provide:
1. Mailcow production-readiness summary (DNS/auth/delivery/retry posture)
2. Realtime UX completion summary (DM + social interactions)
3. Encrypted-device UX summary and remaining security review items
4. Reliability/SLO report and recommended Phase 7 scope
