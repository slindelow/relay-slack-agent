# RELAY — Build Status vs Final Output

**Final output target:** Fully working Slack Marketplace plugin for Slack Connect channels, primarily serving CRM-connected CS teams.

---

## Current State (as of 2026-06-08)

| Plan | Scope | Status | Where |
|------|-------|--------|-------|
| 1 — Foundation | DB schema, Slack OAuth, crypto, Celery, `/relay help` | ✅ Merged to main | PRs #1–3 |
| 2 — CRM + Account Registry | HubSpot OAuth, channel registration, question machine, event ingestion | ✅ Complete (PRs #9, #10 pending merge) | PRs #4, #6, #7, #8, #9, #10 |
| 3 — SLA Engine + Alerts | 60s poller, DM alert cards, claim/snooze/assign/mark-not-question | ✅ Complete (pending merge) | PR #11 |
| 4 — Source Connectors | pgvector, Google Drive, GitHub, embedding pipeline, retrieval | ✅ Merged to main | PR #12 |
| 5 — Drafting + Approval | Evidence bundle, LLM draft, Slack modal, bot-posted response | ✅ Merged to main | PR #13 |
| 6 — Feedback + Memory | Knowledge entries, impact metrics, `/relay ask`, `/relay pulse` | ✅ Complete locally | Local branch `claude/plan-6-feedback-memory` |
| 7 — Marketplace Readiness | KMS encryption, deletion flows, privacy policy, reviewer sandbox | ✅ Complete locally — legal pages, scope doc, health/Sentry, deletion/purge, KMS, user erasure, reviewer sandbox, CI Celery health | Local branch `codex/plan-7-marketplace-readiness` |
| 8 — Security Hardening | Admin/CSM guards, tenant-scoped action lookups, OAuth/erasure token hardening, deletion/audit cleanup, log redaction, retry/model config cleanup | ✅ Complete locally — full suite green | Local branch `claude/plan-8-security-hardening` |

---

## Immediate Next Steps

1. Push Plan 8 branch and open a PR for final review.
2. Merge Plan 6/7/8 PRs in dependency order once CI/review are green.

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
- ✅ US-007: Added admin feedback export endpoint with Slack auth.test, admin role check, JSONL streaming, and day-window clamp.
- ✅ US-008: Added `/relay pulse [account]` account digest with summary and detailed Block Kit responses.
- ✅ Plan 6 draft PR opened: #14.

## Plan 7 Progress

- ✅ US-005: Added public `/privacy`, `/terms`, and `/sub-processors` pages.
- ✅ US-006: Added `docs/marketplace/scope-justification.md`.
- ✅ US-008: Added optional Sentry initialization, dependency-aware `/health` (`db`, `redis`, 503 on dependency failure), Redis CI service, and `celery inspect ping` worker health step.
- ✅ US-002: Added workspace deletion job table/model, `/relay delete-workspace-data` confirmation modal, workspace-scoped Celery deletion task, Slack uninstall token revocation + deletion enqueue, and CI-backed full-data-tree DB test.
- ✅ US-003: Added App Home "Disconnect + Purge" flow and connector-id-scoped purge task for chunks/documents + disconnected marker.
- ✅ US-001: Added KMS columns, AWS KMS provider abstraction, DEK helpers, mocked KMS tests, workspace-DEK write/read paths with global-key fallback, legacy fallback marker, and offline re-encryption script.
- ✅ US-004: Added signed-confirmation admin user erasure endpoint, `users.deleted_at`, and anonymization of user PII plus nullable actor references.
- ✅ US-007: Added idempotent `scripts/seed_reviewer_sandbox.py` and `docs/marketplace/reviewer-walkthrough.md`.
- ✅ Plan 7 complete locally. The full-data-tree deletion test skips on this machine because Postgres/Docker are unavailable, and is set up to run under CI's Postgres service.

## Plan 8 Progress

- ✅ Added centralized `require_relay_admin()` and `require_relay_csm()` authorization helpers.
- ✅ Added admin checks for workspace deletion, channel registration, connector purge, HubSpot install, and admin export/erasure flows.
- ✅ Added CSM/admin checks for draft open, generate, send, discard, and regenerate actions.
- ✅ Resolved Slack workspaces from `team_id` before tenant-scoped action lookups and tightened explicit `workspace_id` predicates.
- ✅ Hardened HubSpot OAuth state and individual-erasure confirmation tokens with signed timestamps and expiry.
- ✅ Guarded empty erasure secrets, validated HubSpot workspace binding, redacted HubSpot response bodies, and made AWS KMS configuration fail explicitly until implemented.
- ✅ Cleaned up deletion cascade coverage, SLA token revocation field usage, drafting retry behavior, dead code, and configurable summary model.
- ✅ Verification on 2026-06-08: `.venv/bin/python -m pytest -q` — 248 passed, 20 skipped, 1 existing Starlette/httpx warning; compileall and `git diff --check` passed.
