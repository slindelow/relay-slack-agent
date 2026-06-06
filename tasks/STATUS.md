# RELAY — Build Status vs Final Output

**Final output target:** Fully working Slack Marketplace plugin for Slack Connect channels, primarily serving CRM-connected CS teams.

---

## Current State (as of 2026-06-06)

| Plan | Scope | Status | Where |
|------|-------|--------|-------|
| 1 — Foundation | DB schema, Slack OAuth, crypto, Celery, `/relay help` | ✅ Merged to main | PRs #1–3 |
| 2 — CRM + Account Registry | HubSpot OAuth, channel registration, question machine, event ingestion | ✅ Complete (PRs #9, #10 pending merge) | PRs #4, #6, #7, #8, #9, #10 |
| 3 — SLA Engine + Alerts | 60s poller, DM alert cards, claim/snooze/assign/mark-not-question | ✅ Complete (pending merge) | PR #11 |
| 4 — Source Connectors | pgvector, Google Drive, GitHub, embedding pipeline, retrieval | ✅ Merged to main | PR #12 |
| 5 — Drafting + Approval | Evidence bundle, LLM draft, Slack modal, bot-posted response | ✅ Merged to main | PR #13 |
| 6 — Feedback + Memory | Knowledge entries, impact metrics, `/relay ask`, `/relay pulse` | 🟡 In progress — US-001/002/003/004 advanced | Local branch `claude/plan-6-feedback-memory` |
| 7 — Marketplace Readiness | KMS encryption, deletion flows, privacy policy, reviewer sandbox | ❌ Not started | — |

---

## Immediate Next Steps

1. Add admin feedback export (US-007).
2. Add `/relay pulse` account digest (US-008).

---

## Critical Path to Marketplace

```
Merge #9, #10, #11
       ↓
Plan 4: Source Connectors + pgvector
       ↓
Plan 5: Drafting + Approval (first full product loop)
       ↓
Plan 6: Feedback + Memory + Pulse
       ↓
Plan 7: KMS + Deletion + Privacy + Sandbox → SUBMIT
```

---

## PRD Index

| File | Plan | Status |
|------|------|--------|
| `tasks/prd-plan4-source-connectors.md` | 4 — Connectors | Ready to execute |
| `tasks/prd-plan5-drafting-approval.md` | 5 — Drafting | Ready to execute |
| `tasks/prd-plan6-feedback-memory.md` | 6 — Memory + Pulse | Ready to execute |
| `tasks/prd-plan7-marketplace-readiness.md` | 7 — Marketplace | Ready to execute |

---

## Known TODOs (non-blocking)

- Redis dedup on ingestion (idempotency key check before classify) — in `relay/worker/tasks.py`
- HubSpot company upsert — stubbed in `relay/worker/hubspot_tasks.py`
- `Question.snoozed_until` field is dead schema — remove in a future migration (Snooze table is authoritative)

## Plan 6 Progress

- ✅ US-001: Added `0006_plan6_memory.py` and `KnowledgeEntry`; Codex fixed ORM/migration FK drift so tenant-scoped metadata matches Alembic.
- ✅ US-002: Added `index_approved_response()` and wired sent drafts into resolution memory indexing.
- ✅ US-003: Retrieval cites memory chunks as `relay_memory` and increments `reuse_count`.
- ✅ US-004: Added `/relay ask <question>` routing and ephemeral source results.
- ✅ US-005: Added App Home impact metrics section with 30-day SLA met rate, draft accepted rate, median time to send, and total handled count.
- ✅ US-006: Added App Home accuracy section with 7-day correction count, classification accuracy, and feedback export link.
- ⏭️ Next: US-007 admin feedback export endpoint.
