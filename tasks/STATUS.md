# RELAY — Build Status vs Final Output

**Final output target:** Fully working Slack Marketplace plugin for Slack Connect channels, primarily serving CRM-connected CS teams.

---

## 🟢 Live Beta Validation (2026-06-24)

Core product loop **validated end-to-end** in the live "RELAY Beta" Slack Connect workspace on Railway. 8/14 checklist steps PASS (1,2,3,5,7,9,10,11). Full chain works: customer question → classify → SLA DM alert → claim → **MCP-powered cited draft (Sonnet 4.6)** → review modal → bot posts approved response → resolved; `/relay ask` returns cited results from an indexed GitHub source.

Six live bugs fixed this session (all on `main`): channel-mention parser (`1c27eeb`), worker async event-loop/NullPool (`cc3f63d`), embedding dims 1024 (`0772760`), retired model IDs (`d5bf4a6`), App Home draft-review surfacing (`f1152d9`), draft-modal button style (`36bb082`). Plus Slack app config (escape/interactivity/events/scope/messages-tab) and Voyage payment method. See `docs/HANDOFF.md` 2026-06-24 entry and `docs/deployment/beta-validation-checklist.md` for details.

Remaining checklist: 4 HubSpot (deferred), 6 setup-complete (3/4), 8 SLA timer, 12 pulse ARR (needs HubSpot), 13 delete, 14 uninstall.

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
| 9 — Private Beta Launch | Railway deployment, Slack manifest/install path, onboarding UX, connector/CRM readiness, beta encryption smoke, live beta validation, external docs | 🚧 Active next plan | `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md` |
| 10 — MCP + Slack RTS Context | MCP context tools, Slack Real-Time Search user consent, context audit logs, ask/drafting context boundary | ✅ Complete locally on `codex/mcp-rts-beta-foundation` | Local branch |

---

## Immediate Next Steps

1. Keep Plan 9 as the active shared plan in `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md`.
2. Split Plan 9 into scoped PRs: deployment/distribution, onboarding UX, connector/CRM readiness, production KMS, live beta validation, and external packaging.
3. Merge any remaining Plan 6/7/8 branches before product behavior branches that depend on them.

---

## Critical Path to Private Beta, Then Marketplace

```
Plan 9A: deployable beta stack + Slack manifest/install path
       ↓
Plan 9B: admin onboarding + /relay settings + first-admin bootstrap
       ↓
Plan 9C: HubSpot upsert + admin-driven source connector setup
       ↓
Plan 9D: Railway beta preflight + encryption smoke
       ↓
Plan 9E: live Slack Connect beta validation
       ↓
Marketplace submission package
```

---

## PRD Index

| File | Plan | Status |
|------|------|--------|
| `tasks/prd-plan4-source-connectors.md` | 4 — Connectors | Ready to execute |
| `tasks/prd-plan5-drafting-approval.md` | 5 — Drafting | Ready to execute |
| `tasks/prd-plan6-feedback-memory.md` | 6 — Memory + Pulse | Ready to execute |
| `tasks/prd-plan7-marketplace-readiness.md` | 7 — Marketplace | Ready to execute |
| `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md` | 9 — Private Beta Launch | Active source of truth |

---

## Known TODOs (non-blocking)

- **Customer-facing approved-response UX** (`relay/slack/draft_actions.py:275`) — bot posts `Posted by RELAY on behalf of @<rawUserID> after their approval`; shows raw Slack ID and exposes internal approval framing to the customer. Needs a cleaner client-facing format. (Flagged during 2026-06-24 live validation.)
- **`slack-app-manifest.yaml` is stale** — has placeholder URLs and disabled Messages Tab / missing `message.channels` + `channels:history`. Update to match the live Slack config (see `docs/HANDOFF.md`) for correct re-installs / Marketplace submission.
- **`classifier` import depends on `PYTHONPATH=/app`** (manual Railway var) — make durable by packaging `classifier` in pyproject or exporting PYTHONPATH in `scripts/entrypoint.sh`.
- (Optional) Auto-generate draft on **Claim** to match the spec's "claim → draft modal" flow (currently a separate "Generate draft" action).
- Redis dedup on ingestion (idempotency key check before classify) — in `relay/worker/tasks.py` — next Codex task on `codex/mcp-rts-beta-foundation`
- `Question.snoozed_until` field is dead schema — remove in a future migration (Snooze table is authoritative)
- Railway beta uses `KMS_PROVIDER=none` plus `TOKEN_ENCRYPTION_KEY`; AWS KMS remains the later hardened production path.
- Admin-driven connector setup exists for beta; full OAuth-based connector onboarding remains post-beta polish.

## Plan 9 Progress

- ✅ Created active Plan 9 source of truth in `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md`.
- ✅ Added private-beta Railway deployment runbook in `docs/deployment/private-beta-railway.md`.
- ✅ Kept AWS deployment runbook in `docs/deployment/private-beta-aws.md` as the later hardening path.
- ✅ Added checked-in Slack app manifest in `slack-app-manifest.yaml`.
- ✅ Added minimal container artifacts (`Dockerfile`, `.dockerignore`) for web/worker/beat services.
- ✅ Added public private-beta install page at `/`.
- ✅ Added `/relay settings` setup summary and first-admin bootstrap for workspaces with zero admins.
- ✅ Replaced HubSpot sync stub with workspace-scoped company-to-`CustomerAccount` upsert.
- ✅ Enabled `KMS_PROVIDER=aws` provider selection with `KMS_KEY_ID` validation for later AWS hardening.
- ✅ Added KMS smoke script (`scripts/smoke_kms.py`) with Railway local-mode support and AWS IAM/runbook instructions.
- ✅ Added manual private beta acceptance checklist in `docs/deployment/private-beta-acceptance.md`.
- ✅ Added beta GitHub/Google Drive connector setup modals, encrypted credential storage, and sync enqueue from `/relay settings`.
- ✅ Added DB-backed Slack installation store tests.
- 🚧 Next: deploy Railway beta, run beta preflight/live smoke, then run live Slack Connect beta validation.
- ✅ Added MCP + Slack RTS context foundation locally: governed context contracts, MCP facade, Slack Search consent, encrypted per-user search tokens, context tool logs, `/relay ask` + draft context routing.
- 🚧 Next: implement Redis idempotency, then resume Railway live Slack validation with `/slack/search/oauth_redirect` configured.

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
