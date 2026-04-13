Top-level objective:
Upgrade the existing Freeparty codebase from “strong foundation / MVP+” into a cleaner, more robust next-stage social platform baseline.

Constraints:
- Keep Django + PostgreSQL + Redis + Celery + Channels + Daphne.
- Keep the existing multi-app layout.
- Keep Docker support intact.
- Preserve federation-ready schema direction.
- Favor incremental refactors over rewrites.
- Do not introduce unnecessary new frameworks unless there is a strong reason.
- Do not delete working features unless replacing them with something clearly better and compatible.
- Keep Apache reverse-proxy compatibility assumptions intact.

Work style requirements:
1. First inspect the existing codebase and summarize:
   - current strengths
   - weak spots
   - duplicated logic
   - permission risks
   - missing tests
   - missing API parity
2. Then implement changes in small, coherent increments.
3. Prefer service/helper abstractions where repeated logic exists.
4. Preserve migrations if possible; add new migrations only where needed.
5. Update README / status docs / implementation docs when behavior changes.

Priority goals for this pass:

PHASE 2 PRIORITY A — permission and ownership correctness
Implement a dedicated permission layer for posts and comments.

Requirements:
- Audit every create/edit/delete/report/follow/block-like pathway for authorization correctness.
- Add reusable permission helpers or service functions for:
  - can_view_post
  - can_edit_post
  - can_delete_post
  - can_comment_on_post
  - can_edit_comment
  - can_delete_comment
  - can_view_actor
  - can_follow_actor
- Ensure blocked relationships are respected consistently in views, timelines, search results, profile pages, and engagement actions.
- Ensure soft-deleted posts/comments cannot be edited or re-engaged with improperly.
- Centralize duplicated ownership checks if they currently exist across views/templates/forms.
- Add tests for permission edge cases.

PHASE 2 PRIORITY B — pagination and query hygiene
Add pagination to places likely to grow.

Requirements:
- Add pagination to:
  - public timeline
  - home timeline
  - actor profile post lists
  - search results
  - notifications list
- Use a consistent pagination style across templates and APIs.
- Review N+1 query risks and improve with select_related / prefetch_related where appropriate.
- Keep timeline logic out of templates and avoid bloated views.
- If helpful, add selectors/query helper modules for repeated list queries.
- Document any meaningful query optimizations.

PHASE 2 PRIORITY C — privacy and relationship controls
Add stronger account-level privacy support.

Requirements:
- Implement optional private account mode.
- If an account is private:
  - follow requests become pending
  - owner can approve/reject requests
  - follower-only visibility is enforced properly
- Add models/fields/services if needed, but integrate with the existing social graph cleanly.
- Provide UI for:
  - toggling private account
  - approving/rejecting pending follow requests
- Ensure privacy rules affect:
  - timelines
  - profile visibility
  - post visibility
  - API endpoints
  - search exposure where appropriate
- Add tests for private/public transitions and follow request flows.

PHASE 2 PRIORITY D — stronger moderation workflow
Upgrade moderation from basic reporting to an actual workflow.

Requirements:
- Build moderation review queue pages in admin and/or staff views.
- Make reports easier to review and act upon.
- Add structured moderation states such as:
  - open
  - under_review
  - resolved
  - dismissed
  - actioned
- Support linking moderation actions to reports.
- Add moderator notes or action notes if not already implemented fully.
- Improve admin usability with filters, list displays, and quick triage.
- Ensure moderation actions are audit-friendly.
- Do not overbuild a giant trust-and-safety suite; keep it practical and extensible.

PHASE 2 PRIORITY E — notifications improvement
Improve notifications UX and correctness.

Requirements:
- Audit notification creation pathways for:
  - follows
  - likes
  - reposts
  - replies
  - mentions
- Prevent obvious duplicate-notification bugs where appropriate.
- Add better notification list UX:
  - unread/read distinction
  - optional filter tabs or type filters
  - grouped display if reasonable
- Keep websocket support scaffold-compatible, but do not over-engineer realtime if current plumbing is minimal.
- Add tests around notification creation for common pathways.

PHASE 2 PRIORITY F — API parity
Bring the API up to parity with newer UI actions.

Requirements:
- Audit what UI actions currently exist without equivalent API support.
- Add API support for:
  - comments create/edit/delete
  - post edit/delete
  - privacy settings updates
  - follow request approve/reject if private accounts are added
  - notifications mark read / mark all read if missing or incomplete
- Keep serializer/viewset/APIView organization clean.
- Preserve permission enforcement in API endpoints exactly as in HTML views.
- Use consistent response shapes and status codes.
- Add API tests for core actions.

PHASE 2 PRIORITY G — tests
Substantially improve test coverage.

Minimum test areas:
- auth and verification smoke tests
- username/handle validation
- post creation/edit/delete permissions
- comment creation/edit/delete permissions
- visibility rules
- block/mute/follow rules
- private-account follow request flow
- notification generation
- moderation report state transitions
- key API endpoints
- basic pagination behavior

Testing expectations:
- Prefer focused model/service/view/API tests over giant brittle integration tests.
- Keep test layout organized by app.
- Add fixtures/factories/helpers if needed to reduce repetition.
- Make tests fast and understandable.

PHASE 2 PRIORITY H — code health and refactor pass
Perform a targeted refactor pass where it clearly improves maintainability.

Requirements:
- Extract duplicated logic from views into services/selectors/helpers where appropriate.
- Improve naming consistency if there are obvious mismatches.
- Add type hints where practical.
- Keep templates clean and avoid pushing business rules into them.
- Avoid large rewrites unless necessary.
- Update docs if you change architecture or flows.

UI/UX expectations:
- Preserve current accessibility controls and avoid regressing them.
- Maintain keyboard accessibility and reasonable semantic HTML.
- Keep the existing styling/theme direction unless a small improvement is clearly helpful.
- Favor practical moderation/privacy/notification UX over flashy redesigns.

Documentation deliverables:
Update:
- README.md if setup or behavior changes
- PROJECT_STATUS.md to reflect the new implementation state
- implementation_reference.md with any new conventions
- OPERATIONS.md if moderation/admin/runtime workflows change

At the end, provide:
1. A concise audit of what you found
2. A summary of changes made
3. A list of migrations added
4. A list of tests added
5. Any follow-up recommendations for Phase 3

Important implementation guidance:
- Respect the existing federation-ready base, but do not try to fully implement federation in this pass.
- Do not rip out current working code just to make it “cleaner.”
- Prefer durable social-product correctness over cosmetic additions.
- Prioritize permissions, privacy, moderation, API completeness, and tests.

Success criteria:
- Existing app still runs cleanly in Docker
- Migrations apply cleanly
- Core flows still work
- New privacy and moderation workflows function correctly
- API and UI are more aligned
- Test coverage meaningfully improves
- Project remains organized and extensible

Execution tasks requested (1 and 2):

1) Task list for Priority D (stronger moderation workflow)
- [x] Add report status expansion:
  - [x] Add `under_review` and `actioned` status values
  - [x] Add migration for any status/model field changes
- [x] Improve moderation queue in staff views:
  - [x] Add queue filters by status, reason, date, actor, post
  - [x] Add quick actions for status transitions
  - [x] Add clear report detail links from queue rows
- [x] Link moderation actions to reports reliably:
  - [x] Ensure action records always capture moderator and timestamp
  - [x] Ensure action notes are preserved and visible in report detail
- [x] Improve admin moderation UX:
  - [x] Add list filters and search improvements in admin classes
  - [x] Add sensible default ordering and list_display fields
- [x] Add audit-friendly behavior:
  - [x] Prevent silent overwrite of prior moderation states
  - [x] Record reviewed_by/reviewed_at consistently on updates
- [x] Add tests:
  - [x] Report state transition tests
  - [x] Moderator permission tests (staff vs non-staff)
  - [x] Action/note linkage tests
- [x] Documentation updates:
  - [x] Update `OPERATIONS.md` moderation workflow section
  - [x] Update `PROJECT_STATUS.md` and `implementation_reference.md`

2) Task list for Priority E + F slice (notifications correctness + API parity)
- [x] Audit notification creation paths:
  - [x] Follow notifications
  - [x] Like notifications
  - [x] Repost notifications
  - [x] Reply/mention notifications
- [x] Prevent duplicate notifications:
  - [x] Add dedupe guard for same actor/type/target within safe window or object uniqueness rule
  - [x] Ensure toggles (like/unlike, repost/remove) do not spam duplicates
- [x] Improve notification UX behavior:
  - [x] Keep unread/read visual distinction consistent
  - [x] Keep filter tabs functioning with pagination
  - [x] Add grouped display if lightweight and low-risk
- [x] Add missing notifications API actions:
  - [x] Mark single notification as read
  - [x] Mark all notifications as read
  - [x] Add tests for both endpoints and permission scope
- [x] Complete API parity for comments:
  - [x] Add comment create/edit/delete API endpoints
  - [x] Reuse centralized permission helpers from HTML flows
  - [x] Add API tests for owner and non-owner scenarios
- [x] Validate websocket compatibility:
  - [x] Ensure existing consumer payload still works after notification changes
- [x] Documentation updates:
  - [x] Update `README.md` API parity list
  - [x] Update `PROJECT_STATUS.md` and `implementation_reference.md`

Done criteria for this requested pair:
- [x] `python manage.py check` passes
- [x] Relevant test suites pass (moderation, notifications, posts/social/api)
- [x] New migrations apply cleanly
- [x] Docs updated to reflect implemented behavior

3) Phase 3 kickoff (initial hardening slice)
- [x] Add request observability middleware:
  - [x] Generate/propagate `X-Request-ID`
  - [x] Attach request ID to all responses
- [x] Add slow-request visibility:
  - [x] Log warning when request duration exceeds configurable threshold
  - [x] Add `REQUEST_SLOW_MS` setting support
- [x] Add initial tests:
  - [x] Request ID generation behavior
  - [x] Request ID passthrough behavior
  - [x] Slow request logging behavior