# Phase 7.0: PM Security Gate Closure Tracking

**Increment:** 7.0 (PM Gate)  
**Target Completion:** Week 1-2  
**Owner Assignment Needed:** Yes  

This document converts ADR 0001 threat model checklist into actionable tracking items for the PM security gate.

## Threat Model Closure Items

| # | Item | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Plaintext leakage audit (DB, logs, traces, exceptions) | _ASSIGN_ | not-started | Search code for `message.text` in logs; check `.get_logs()` output; trace exception paths |
| 2 | Replay protections and message ordering semantics documented | _ASSIGN_ | not-started | Document at `apps/private_messages/docs/` with tests in `PrivateMessagesOrderingTests` |
| 3 | Forward secrecy strategy and limits documented | _ASSIGN_ | not-started | Bind to `key_epoch` ratchet model; document in RFC-style ADR |
| 4 | Key compromise recovery flow defined and tested | _ASSIGN_ | not-started | Test: revoke key, verify old messages, send new messages; update `apps/private_messages/tests/KeyCompromiseTests.py` |
| 5 | Device loss and key revocation flow defined | _ASSIGN_ | not-started | Owner doc in user support playbook; create `scripts/pm_key_revoke.py` CLI tool |
| 6 | Safety number mismatch UX tested (false-positive/negative rates) | _ASSIGN_ | not-started | Run `SafetyFingerprintContractTests` with edge cases; measure collision rates |
| 7 | Metadata minimization review (sender/recipient/timestamps/indexes) | _ASSIGN_ | not-started | Audit DB schema indexes; check query logs for information leakage |
| 8 | Abuse and legal escalation pathways defined | _ASSIGN_ | not-started | Draft moderation runbook for encrypted content; coordinate with moderation team |
| 9 | External crypto review and recording | _ASSIGN_ | not-started | Schedule external reviewer; document findings in `docs/security/` |
| 10 | Security sign-off completed | _ASSIGN_ | not-started | Final approval gate—must wait for all 9 items complete |

## Incremental Rollback Triggers (Week 1.3)

Define per-item rollback criteria:

| Item | If This Happens | Rollback Action |
|------|-----------------|-----------------|
| 1 | Plaintext found in logs | Revert log capture in `private_messages.services` |
| 2 | Message ordering failures in tests | Revert `EncryptedMessageEnvelope.sequence_num` logic |
| 4 | Key compromise recovery fails | Keep `key_rotation_disabled=True` in settings until resolved |
| 5 | Lost-device flow not documented | Keep `FEATURE_PM_E2E_ENABLED=False` and block external PM exposure |
| 9 | Crypto review finds issue | Halt PM rollout update security findings, fix, re-review |

## Execution Checklist

- [ ] Week 1: Assign owners to items 1-10
- [ ] Week 1: Define notification and escalation contacts for each owner
- [ ] Week 1: Identify blocking dependencies (e.g., #9 blocks #10)
- [ ] Week 2: Complete items 1-3 (foundational audits)
- [ ] Week 2: Complete items 4-8 (threat model coverage)
- [ ] End of Week 2: Item #9 (external review) in progress or complete
- [ ] After Week 2: Item #10 (sign-off) ready to proceed

## Links

- ADR foundation: [docs/adr/0001-pm-e2e-foundation.md](docs/adr/0001-pm-e2e-foundation.md)
- Phase 7 roadmap: [phases_phase_7.md](phases_phase_7.md)
- Test base: `apps/private_messages/tests.py`
