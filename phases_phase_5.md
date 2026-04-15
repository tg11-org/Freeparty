Top-level objective:
Deliver user-facing direct messages safely and harden abuse reporting into a structured, severity-aware moderation intake flow.

Context baseline entering Phase 5:
- Phase 4 delivered media workflows, moderation parity, and PM/E2E backend foundations.
- PM schema, feature flagging, and deterministic safety fingerprint contracts now exist.
- Report workflow currently supports freeform/legacy reason values but does not yet enforce structured categories or severity routing.

Constraints:
- Keep PM rollout behind explicit feature gating until security review items are satisfied.
- Do not introduce plaintext message persistence paths.
- Keep DM permissions block-aware and reversible.
- Keep report hardening compatible with existing moderation queue workflows.

Work style requirements:
1. Ship in narrow slices with tests.
2. Keep PM initiation/navigation separate from full encrypted send/receive rollout.
3. Add docs/runbook updates with each completed slice.
4. Preserve migration safety and rollback notes.

Success criteria for Phase 5:
- Users can initiate and manage direct conversation shells safely.
- PM sending/reading flows progress without breaking encrypted-envelope-only storage guarantees.
- Report submission uses structured reason taxonomy with severity-aware routing context.
- Staff can filter and triage higher-risk reports faster.

PHASE 5 PART A - DM Initiation and Navigation
Goal:
Expose a user-facing direct conversation start flow on top of the existing PM foundation.

Requirements:
- Add DM list/detail shell views.
- Add actor-profile DM initiation action.
- Prevent self-DM and blocked-account DM initiation.
- Reuse existing direct conversation when one already exists.

PHASE 5 PART B - Report Taxonomy Hardening
Goal:
Replace generic report intake with structured categories and severity-aware metadata.

Requirements:
- Add policy-backed report reasons.
- Derive or persist severity for queue routing.
- Update report submission UI to show category options.
- Keep moderation queue/detail/API compatible.

PHASE 5 PART C - Encrypted Send/Receive Flow
Goal:
Add minimal encrypted message compose/read surfaces after initiation path is stable.

Requirements:
- Add encrypted envelope compose flow inside DM detail.
- Derive sender/recipient active identity keys for one-to-one threads.
- Keep HTML rendering metadata-only; do not render plaintext or ciphertext bodies back to users.
- Add tests for envelope send/store success and blocked-key states.

PHASE 5 PART D - Key Change and Verification UX
Goal:
Surface safety fingerprint verification and key-change warnings to users.

Requirements:
- Show safety fingerprint in conversation detail when both active keys exist.
- Add explicit missing-key warning when encrypted send is not available.
- Add key change warning contract and follow-up UX tasks.

PHASE 5 PART E - Moderation Queue Routing Improvements
Goal:
Use report severity and category data to improve moderator triage and escalation.

Requirements:
- Add dashboard filters for severity/category.
- Add detail-page severity visibility and escalation hints.
- Preserve staff API compatibility.

Execution plan by increments:

Increment 5.0
- DM initiation MVP (HTML list/create/detail shell).

Execution tasks (Increment 5.0):
- [x] Add private message list/detail views and routes.
- [x] Add actor profile DM initiation action.
- [x] Add block/self protections and direct-conversation dedupe.
- [x] Add tests for DM initiation flow.

Increment 5.1
- structured report reasons + severity metadata + intake form UX.

Execution tasks (Increment 5.1):
- [x] Add report reason taxonomy and severity mapping.
- [x] Add report form page with structured category selection.
- [x] Update actor/post report entry points to use structured intake flow.
- [x] Add tests for normalization, severity, and submission flow.

Increment 5.2
- encrypted envelope compose/store flow in DM detail.

Execution tasks (Increment 5.2):
- [x] Add encrypted envelope compose form to DM detail.
- [x] Derive sender/recipient active keys for direct-thread sends.
- [x] Keep DM detail rendering metadata-only for stored encrypted envelopes.
- [x] Add tests for successful encrypted envelope storage and missing-key blocked state.

Increment 5.3
- verification and key-change UX hardening.

Execution tasks (Increment 5.3):
- [x] Surface key-change warning contract in conversation detail.
- [x] Add tests covering changed remote identity key state.
- [x] Add docs for acknowledgment workflow and rollout expectations.
- [x] Add user key bootstrap action to unblock missing-local-key DM send states.

Increment 5.4
- moderation queue routing improvements.

Execution tasks (Increment 5.4):
- [x] Add moderation dashboard severity/category filters.
- [x] Add severity/category visibility in report detail and API payloads.
- [x] Add tests for severity/category queue filtering.

Increment 5.5
- development-only ciphertext preview for envelope debugging.

Execution tasks (Increment 5.5):
- [x] Add `FEATURE_PM_DEV_CIPHERTEXT_PREVIEW` feature flag.
- [x] Gate ciphertext rendering to `DEBUG=True` plus preview flag.
- [x] Add PM HTML tests for preview enabled/disabled behavior.

Increment 5.6
- browser-side encryption/decryption workflow.

Execution tasks (Increment 5.6):
- [x] Add browser identity key registration endpoint (`POST /messages/keys/register/`) that stores only public key metadata.
- [x] Add DM detail Web Crypto flow: encrypt plaintext before submit and decrypt envelopes on read when local private key is available.
- [x] Keep server persistence envelope-only (`ciphertext`, `nonce`, key ids) with no plaintext storage.
- [x] Add PM tests for browser-key registration payload validation and active-key rotation behavior.
- [x] Harden browser send UX with clear missing-device-key recovery messaging and disabled-send gating.
- [x] Add `novalidate` to the browser E2E send form to avoid hidden required-field browser validation failures.

Acceptance gate per increment:
- python manage.py check passes.
- New/changed tests pass for touched apps.
- No unresolved lint/type errors in changed files.
- Docs updated for behavior and operations changes.

Documentation deliverables for Phase 5:
Update after each relevant increment:
- README.md
- PROJECT_STATUS.md
- implementation_reference.md
- OPERATIONS.md

At end of Phase 5, provide:
1. DM initiation and encrypted-envelope workflow summary
2. Verification UX status and remaining crypto review gates
3. Report taxonomy + severity routing summary
4. Remaining risks and recommended Phase 6 scope
