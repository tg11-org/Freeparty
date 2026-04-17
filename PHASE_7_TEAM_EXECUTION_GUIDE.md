# Phase 7 Team Execution Guide

**Prepared:** 2026-04-16 Evening  
**For:** Platform + Backend Team  
**Status:** Ready for handoff - Increments 7.0-7.2 infrastructure complete

---

## Quick Start for Continuing Phase 7 Execution

### What's Complete (Ready to Build On)

✅ **Increment 7.0: PM Security Gate**
- Staged rollout policy infrastructure (DISABLED/ALLOWLIST/BETA/GENERAL)
- Dual-gate enforcement (feature flag + per-actor policy)
- Admin UI for managing PM cohorts
- Comprehensive testing (7/7 tests passing)
- Operations runbook with rollback procedures

✅ **Increment 7.1: PM Key Lifecycle**
- Key compromise tracking (compromised flag + reason + timestamp)
- Rotation cooldown protection (5-minute minimum)
- Public key validation (base64 + minimum length)
- Audit trail (KeyLifecycleAuditLog model + 8 event types)
- Database migrations applied

✅ **Increment 7.2 Infrastructure (skeleton ready)**
- Dead-letter model enhanced (terminal_reason field)
- Dead-letter inspection command (`dead_letter_inspect --limit`)
- All migrations applied
- Ready for task reliability wrapper implementation

### Safety Defaults Enforced
```python
# All risky features disabled by default:
FEATURE_PM_E2E_ENABLED=False                    # PM disabled until gate closure
FEATURE_PM_WEBSOCKET_ENABLED=False              # Polling fallback only  
FEATURE_LINK_UNFURL_ENABLED=False               # Unfurl disabled until validation
PMRolloutPolicy.stage=DISABLED                  # No actors eligible for PM
```

---

## Immediate Actions (Next 3 Days)

### Team Lead: Assign Owners
```
7.2: Async Reliability/Dead-Letter   → Backend Lead
7.3: Moderation Escalation/SLA       → Moderation/Safety Lead
7.4: Federation Inbound Allowlist    → Federation Lead
7.5: Federation Outbound Delivery    → Federation Lead
7.6: Observability Dashboards        → Platform/Ops Lead
7.7: Failure Drills                  → Ops Lead + Engineering Lead
```

### Owner Actions (By End of Day 1)
1. Read [PHASE_7_IMPLEMENTATION_STATUS.md](PHASE_7_IMPLEMENTATION_STATUS.md) for your increment
2. Review the execution tasks (4-6 per increment)
3. Create subtasks in your tracker (estimate 1-2 hours each task)
4. Schedule 2-3 hour focused work blocks (minimally fragmented)
5. Reach out if requirements are unclear

---

## Testing Requirements for Phase 7

All increments must have:
- [ ] Unit tests for new behavior (success + failure paths)
- [ ] Integration test for end-to-end workflow (where applicable)
- [ ] Admin interface test (if model added)
- [ ] Operations/runbook validation (manual walkthrough of incident scenario)
- [ ] Backward compatibility test (existing behavior still works)

**Test Files to Update:**
- `apps/private_messages/tests.py` — PM tests (7.0-7.1 done, 7.2 ready)
- `apps/core/tests.py` — Async reliability tests (7.2 pending)
- `apps/moderation/tests.py` — Escalation tests (7.3 pending)
- `apps/federation/tests.py` — Federation tests (7.4-7.5 pending)

---

## Running Phase 7 Validation

After each increment is "done", run:

```bash
# Overall project health
python manage.py check --deploy

# Run all private_messages tests
python manage.py test apps.private_messages.tests -v 2

# Run dead-letter command (should list any failures)
python manage.py dead_letter_inspect --limit 10

# Verify DB migrations are current
python manage.py showmigrations

# Check for any unhandled import/syntax errors
python manage.py shell -c "import apps.private_messages.services; import apps.core.management.commands.dead_letter_inspect; print('✓ All imports OK')"
```

---

## Critical Upstream Dependencies

| Item | Depends On | Ready? |
|------|-----------|--------|
| 7.2: Async Reliability | 7.0-7.1 (PM foundation) | ✅ Yes |
| 7.3: Moderation SLA | 7.2 (async reliability) | ⏳ Pending 7.2 |
| 7.4-7.5: Federation | 7.2 (async reliability) | ⏳ Pending 7.2 |
| 7.6: Dashboards | 7.2-7.5 (metrics collection) | ⏳ Pending 7.2-7.5 |
| 7.7: Failure Drills | 7.6 (runbooks + dashboards) | ⏳ Pending 7.6 |

**Bottom line:** Get 7.2 stabilize quickly. It's the foundation for everything after.

---

## Phase 7 Milestone Acceptance Criteria

### ✅ Done = Meets All These Criteria

1. **Code:** All execution tasks in increment completed
2. **Tests:** All new behavior has tests (unit + integration)  
3. **Docs:** README/OPERATIONS/implementation_reference updated
4. **Admin:** Any new models registered in admin with appropriate fieldsets
5. **Migrations:** All database migrations applied to staging
6. **Backward Compat:** Existing behavior unaffected (all prior tests still pass)
7. **Runbook:** Incident response procedure documented (if applicable)

### Not Done = Missing Any Of Above

Examples of "not done":
- Code written but tests skipped ("we'll test later")
- Tests passing but docs not updated
- Admin missing but  model created
- Migration generated but not applied
- Runbook not written (how would ops handle this in production?)

---

## Communication During Phase 7 Execution

### Daily Standup Agenda (15 min)
- What I finished yesterday (increment task)
- What I'm working on today (increment task)
- Blockers? (If blocked on X, who owns X?)

### Weekly Sync Agenda (30 min)
- Increment status: On-track / At-risk / Blocked
- Demo of completed work for product
- Any spec/requirement clarifications needed
- Go/no-go assessment for next milestone

### Escalation Path
- Spec ambiguity → Product Lead
- Architecture question → Platform Lead
- Test failure / CI issue → DevOps Lead
- Phase 7 blocker → Engineering Lead

---

## Reference Documents

- [phases_phase_7.md](phases_phase_7.md) — Full Phase 7 scope + increments
- [PHASE_7_KICKOFF.md](PHASE_7_KICKOFF.md) — Week-by-week sprint checklist  
- [PHASE_7_IMPLEMENTATION_STATUS.md](PHASE_7_IMPLEMENTATION_STATUS.md) — Detailed 7.0-7.7 roadmap
- [OPERATIONS.md](OPERATIONS.md) — Ops runbook (includes Phase 7 PM + async reliability sections)
- [PM_SECURITY_GATE_TRACKING.md](PM_SECURITY_GATE_TRACKING.md) — PM threat model checklist + owner assignments
- [PM_KEY_LIFECYCLE_FINDINGS.json](PM_KEY_LIFECYCLE_FINDINGS.json) — Code analysis of key management (for reference)

---

## Success Metrics

By end of Phase 7 (Week 3):
- [ ] 0 unhandled async failures (all failures retrievable via dead-letter queue)
- [ ] PM gate security checklist 100% complete with sign-off
- [ ] Moderation HIGH/CRITICAL reports auto-escalate within 5 minutes
- [ ] Federation pilot partner integrated (real actor fetches + activity exchange working)
- [ ] Observability dashboards live with 5+ alert thresholds active
- [ ] Failure drills completed (all 5 scenarios tested, runbooks updated)
- [ ] Go/no-go sign-off meeting scheduled + passed

---

## Rollback Plan (If Needed)

| Scenario | Rollback Action | Time to Execute |
|----------|-----------------|-----------------|
| PM security issue discovered | Set `FEATURE_PM_E2E_ENABLED=False` + redeploy | < 5 min |
| Async reliability regression | Disable new reliability wrapper + revert commit | 10-15 min |
| Federation outbound causing outages | Set `FEATURE_FEDERATION_OUTBOUND_ENABLED=False` | < 5 min |
| Moderation escalation bug | Revert 7.3 migration + code | 15-20 min |

All rollbacks are non-destructive (no data loss; just feature disable).

---

## Celebrating Phase 7

Once all increments pass acceptance criteria and go/no-go is approved:

🎉 **Public Beta Launch Ready**

- Announce feature set (PM, federation, improved reliability)
- Invite first beta testers to ALLOWLIST cohort
- Monitor closely for first week
- Publish incident response times + uptime stats
- Gather user feedback for Phase 8 planning

---

## Questions?

- Spec  ambiguity → Ask in #phase-7-engineering Slack
- Need help → Tag @platform-lead
- Blocker → Schedule 15-min sync with affected owners

You've got this! 💪

Phase 7 is ambitious but achievable. Focus on incremental validation, clear communication, and disciplined testing. The foundation work (7.0-7.2) is solid. Build from there.

Good luck! 🚀
