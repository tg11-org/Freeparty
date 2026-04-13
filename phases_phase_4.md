Top-level objective:
Deliver media-rich social workflows (images/videos) and prepare Freeparty for secure private communications planning while preserving reliability and moderation guarantees from Phase 3.

Context baseline entering Phase 4:
- Phase 3 observability, anti-abuse controls, moderation API parity, and async reliability foundation are in place.
- Attachment model exists and now supports initial image/video posting flow.
- Home timeline now supports media-focused tab filtering.

Constraints:
- Keep Django + PostgreSQL + Redis + Celery + Channels + Daphne.
- Keep current multi-app architecture and avoid high-risk rewrites.
- Maintain moderation and abuse-control invariants for new media flows.
- Prefer incremental, reversible delivery slices with tests in each slice.
- Avoid claiming cryptographic guarantees before protocol and review gates complete.

Work style requirements:
1. Start each increment with a short audit note:
   - objective
   - risk surface
   - touched apps
   - rollback path
2. Implement in narrow slices with explicit done criteria.
3. Add tests with each slice.
4. Add operational instrumentation for new media/PM pathways.
5. Update docs per increment: README / PROJECT_STATUS / implementation_reference / OPERATIONS.

Success criteria for Phase 4:
- Users can create and consume image/video posts safely and consistently.
- Media-only discovery/timeline views are fast and accurate.
- Media moderation and processing reliability are auditable and test-backed.
- PM + E2E design and implementation plan is explicit, staged, and security-reviewed.

PHASE 4 PART A - Media Posting UX and Validation
Goal:
Enable robust first-class image/video post creation in HTML and API flows.

Requirements:
- Support image/video uploads in post composer:
  - HTML flow with attachment + alt text
  - API serializer support (multipart)
- Validate uploads:
  - content type allowlist
  - size limits
  - user-facing errors
- Persist attachment metadata:
  - type/mime/size/alt text
  - processing state tracking
- Render attachments in post cards/detail views.

Deliverables:
- updated post forms/views/serializers/templates
- attachment validation helpers
- tests for accepted/rejected uploads

Done criteria:
- image/video posts publish successfully
- invalid file types are rejected with clear errors
- media renders correctly in timeline/detail

PHASE 4 PART B - Media-Only Feed and Discovery
Goal:
Offer a dedicated photo/video browsing mode without degrading normal timeline UX.

Requirements:
- Add media-only tab/filter for home and public feeds.
- Ensure pagination preserves tab/filter state.
- Ensure query performance remains stable under media-heavy datasets.
- Add tests for filter correctness and auth/visibility behavior.

Deliverables:
- feed filter query support
- UI tab controls
- query + behavior tests

Done criteria:
- media tab contains only posts with image/video attachments
- normal tab remains unchanged
- no visibility/privacy regressions

PHASE 4 PART C - Media Processing and Reliability
Goal:
Harden media handling pipeline for production use.

Requirements:
- Add async processing hooks for:
  - image normalization / thumbnail generation
  - video metadata extraction
  - failure capture + retries
- Add idempotency keys for processing tasks.
- Capture processing failures in task reliability tables.
- Add reprocessing command(s) for failed media jobs.

Deliverables:
- processing tasks and helpers
- retry policy + runbook entries
- management command for failed media reprocess

Done criteria:
- transient failures retry automatically
- exhausted failures are visible and recoverable

PHASE 4 PART D - Media Moderation and Safety
Goal:
Ensure media content follows same moderation and abuse standards as text posts.

Requirements:
- Extend moderation workflows to include attachment context.
- Add media moderation state transitions and staff tooling.
- Add optional quarantine behavior for flagged media.
- Add tests for visibility enforcement of flagged/removed media.

Deliverables:
- moderation integration for attachments
- staff visibility updates
- policy tests

Done criteria:
- removed/flagged media cannot leak via feed/detail/API
- staff can triage and act on media reports efficiently

PHASE 4 PART E - PM + E2E Foundations (Design + Safe Start)
Goal:
Define and begin private messaging with staged E2E encryption architecture.

Requirements:
- Build PM domain model skeleton:
  - conversation
  - participant
  - encrypted message envelope
- Define E2E key lifecycle model (no unsafe shortcuts):
  - identity keys
  - session keys
  - key rotation/change signaling
- Add local verification UX concept:
  - hex safety fingerprint
  - deterministic visual fingerprint image/identicon
  - explicit key-change warning in client
- Create threat model and crypto review checklist before default enablement.

Deliverables:
- PM schema + service interfaces (feature-flagged)
- E2E protocol decision record (ADR-style section)
- verification UX prototype contract

Done criteria:
- no plaintext PM leakage in designed data path
- verification surfaces are deterministic and testable
- security review gate documented and enforced before rollout

Execution plan by increments:

Increment 4.1 (current)
- Media posting MVP in HTML + rendering.
- Home timeline media-only tab.

Execution tasks (Increment 4.1):
- [x] Add image/video upload fields and validation to post form.
- [x] Create attachments during post creation with mime/type metadata.
- [x] Render media attachments in post card UI.
- [x] Add home feed media-only tab and filter logic.
- [x] Add tests for upload acceptance/rejection and media tab filtering.

Increment 4.2
- API multipart media posting support + public feed media tab parity.
- pagination/query refinements for media views.

Execution tasks (Increment 4.2):
- [x] Add AttachmentSerializer (read) nested in PostSerializer.
- [x] Handle multipart file upload in PostViewSet.perform_create (content-type + size validation).
- [x] Add ?tab=media filter to PostViewSet.get_queryset.
- [x] Prefetch attachments in API queryset.
- [x] Wire mention notifications in PostViewSet.perform_create and CommentViewSet.perform_create.
- [x] Fire REPLY notifications (not MENTION) for comment-on-post author in both HTML and API paths.
- [x] Add tests for API media upload and tab filter.

Increment 4.3
- media async processing tasks + retry/idempotency/failure capture.
- media failure reprocess operations command.

Increment 4.4
- media moderation parity and staff tooling updates.

Increment 4.5
- PM + E2E foundations (feature flagged), safety fingerprint UX, threat model.

Acceptance gate per increment:
- python manage.py check passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs updated for behavior and operations changes.
- Rollback notes included for schema-affecting changes.

Documentation deliverables for Phase 4:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md

At end of Phase 4, provide:
1. Media workflow summary (HTML/API/feed/moderation)
2. Performance snapshot for media feed queries
3. Reliability snapshot for media processing tasks
4. PM/E2E design status and security review outcome
5. Remaining risks and recommended Phase 5 scope
