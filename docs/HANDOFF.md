# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`.

Merged to `main` (Plans 1 + 2 foundation):
- PR #1: collaboration docs
- PR #2: PRD v2.0 + Plan 1 details
- PR #3: Plan 1 foundation scaffold (classifier, DB, crypto, Slack, Celery)
- PR #4: Plan 2 core schema + migration 0002 + RLS on 6 tenant tables
- PR #6: HubSpot OAuth client, routes, encrypted connection storage, sync stub
- PR #7: DB-backed `/relay register`, customer account/channel registration
- PR #8: HANDOFF update

Open PRs (pending merge, in dependency order):
- PR #9 (`claude/plan-2-question-machine`): 5-state question machine, 10 unit tests
- PR #10 (`claude/plan-2-event-ingestion`): Bolt message handler + full Celery classify worker, 5 unit tests
- PR #11 (`claude/plan-3-sla`): Full SLA engine — see below

## Source Of Truth
- `RELAY_PRD.md`
- `docs/PLAN_1_FOUNDATION.md`
- `docs/CLAUDE_OPERATING_BRIEF.md`
- This file

## Stable Branch
`main`

## Collaboration Model
- Branches + PRs.
- Codex uses `codex/...`.
- Claude uses `claude/...`.
- No direct commits to `main`.
- Update this file at the end of every session.
- Commit incrementally — after each completed file or logical chunk.

## Agent Updates

### Claude — 2026-06-05 (session 3, code review)
Branch: `claude/plan-3-sla` → **PR #11 (OPEN, updated)**
Status: Full structural code review completed on Plans 2 + 3. 34 tests pass, 0 warnings.

**Bugs fixed in this session:**

1. **Critical — poller detached-object bug** (`relay/sla/poller.py`):
   The cross-tenant scan closed its session before `_alert_question` ran.
   Question was detached — `next_alert_at`, `alert_count`, `last_alert_at` mutations
   never persisted. Fixed by splitting into Phase 1 (SELECT id+workspace_id only,
   no session state needed) + Phase 2 (load Question inside the workspace-scoped
   session so all mutations commit atomically).

2. **Race condition — double-claim** (`relay/question/machine.py`):
   `_load_question` used a plain SELECT. Two concurrent Bolt handlers could both
   read state="open" and both claim. Fixed with `.with_for_update()`.

3. **Dead code** (`relay/sla/alerts.py`):
   `deadline_secs` on line 51 computed via complex ternary then immediately
   discarded (line 53 recomputed it). Simplified to clean two-branch conditional.

4. **Missing label check** (`relay/worker/tasks.py` on `claude/plan-2-event-ingestion`):
   Classifier confidence was checked without verifying `is_question`. A
   high-confidence "not a question" would create a spurious Question row. Fixed
   by gating all Question creation under `if result_cls.is_question`.

5. **SAWarnings eliminated** (`relay/db/models.py`):
   All 15 pre-existing SAWarning overlaps on composite-FK relationships silenced
   with `overlaps=` annotations throughout the model graph.

Tests run: 34 passed, 0 warnings (unit tests; DB integration tests skipped).

Open TODOs (non-blocking):
- Redis dedup on ingestion (idempotency key check before classify)
- HubSpot company upsert — still stubbed in hubspot_tasks.py
- `Question.snoozed_until` field is dead schema — set nowhere, read by nothing
  (Snooze table is authoritative); remove in a future migration

Next recommended step:
1. Codex: review and merge PRs #9, #10, #11 in order
2. Claude: start Plan 4 — source connectors (GitHub, Notion/Confluence) + retrieval pipeline

### Codex — 2026-06-05
Branch: `codex/plan-2-schema-pr4`, `codex/plan-2-hubspot`, `codex/plan-2-channel-registration`, `codex/handoff-2026-06-05`
Status: Plan 2 slices merged (PRs #4, #6, #7, #8). CI green on all.
Next: Review PRs #9, #10, #11 and merge in order. Start Plan 4 source connectors if Claude hasn't.
