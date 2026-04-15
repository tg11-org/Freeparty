# ADR 0001: PM + E2E Foundation (Feature-Flagged)

Status: Accepted (Foundation Slice)
Date: 2026-04-14
Owner: Freeparty backend

## Context

Freeparty needs private messaging support without introducing plaintext data-path shortcuts or claiming completed cryptographic guarantees before a dedicated review gate.

Phase 4.5 requires a safe start:
- foundational PM schema
- encrypted envelope storage path only
- explicit feature flag disable-by-default posture
- deterministic verification UX contract for later client work

## Decision

1. Add a PM schema foundation in `apps.private_messages`:
- `Conversation`
- `ConversationParticipant`
- `UserIdentityKey`
- `EncryptedMessageEnvelope`

2. Keep runtime PM writing behind `FEATURE_PM_E2E_ENABLED` (default `False`).

3. Enforce encrypted-envelope-only storage contract in service layer:
- message writes require `ciphertext`, `message_nonce`, `sender_key_id`, `recipient_key_id`
- no plaintext message field is accepted or persisted

4. Define verification UX contract for Phase 5:
- deterministic hex safety fingerprint from participant identity keys
- deterministic visual fingerprint (identicon) from same digest input
- explicit key-change warning and acknowledgment UX when identity key rotates

## Key Lifecycle Model (Initial)

- Identity key registration:
  - per-actor identity keys represented by `UserIdentityKey`
  - active key marker supports rotation without deleting history

- Session key epoching:
  - envelope field `key_epoch` marks message encryption epoch
  - later protocol slices will bind key epoch to ratchet/session metadata

- Rotation signaling:
  - `rotated_at` on `UserIdentityKey` marks key transition events
  - future slice adds signed key-change announcements and client warning flow

## Verification Contract (Slice 2 Delivered)

- Safety fingerprint hex contract is implemented in `apps.private_messages.security.compute_safety_fingerprint_hex`.
- Canonicalization contract is order-invariant across participants and normalizes casing/whitespace.
- Visual fingerprint seed contract is implemented in `apps.private_messages.security.compute_identicon_seed`.
- Current seed format is the first 32 hex characters of the safety fingerprint digest.
- Contract tests live in `apps.private_messages.tests.SafetyFingerprintContractTests`.

## Key Change Warning Contract (Slice 5.3 Delivered)

- Per-conversation acknowledgment state is stored on `ConversationParticipant`:
  - `acknowledged_remote_key_id`
  - `acknowledged_remote_key_at`
- DM detail shows a key-change warning whenever the current remote active key id differs from the participant's acknowledged remote key id.
- Warning acknowledgment is explicit and updates the participant-scoped acknowledgment fields.
- This creates a stable contract for later UX improvements without enabling PM by default.

## Threat Model Checklist (Gate Before Default Enablement)

- [ ] Plaintext leakage audit completed for DB writes, logs, traces, and exceptions
- [ ] Replay protections and message ordering semantics documented
- [ ] Forward secrecy strategy and limits documented for selected protocol
- [ ] Key compromise recovery flow defined and tested
- [ ] Device loss and key revocation flow defined
- [ ] Safety number mismatch UX tested for false-positive/false-negative rates
- [ ] Metadata minimization review completed (sender/recipient/timestamps/indexes)
- [ ] Abuse and legal escalation pathways defined for encrypted channels
- [ ] External crypto review completed and recorded
- [ ] Security sign-off completed before toggling `FEATURE_PM_E2E_ENABLED=True`

## Consequences

Positive:
- creates a safe foundation with clear enablement controls
- supports incremental PM rollout without pretending full cryptographic maturity
- gives testable contracts for envelope persistence and key lifecycle scaffolding

Tradeoffs:
- no user-facing PM UX yet
- no final protocol commitment in this slice
- additional migration/model complexity before product exposure

## Rollback Plan

- Keep `FEATURE_PM_E2E_ENABLED=False` to disable PM service entry points.
- If rollback is needed before PM exposure, revert app wiring and migration in a controlled deploy window.
- If data already exists, export/archive PM tables before schema rollback.
