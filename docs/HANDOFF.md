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

### Claude — 2026-06-05 (session 2)
Branch: `claude/plan-3-sla` → **PR #11 (OPEN)**
Status: Plan 3 SLA engine complete. 100 unit tests pass, 2 DB integration tests skip without local Postgres.

**PR #11 contains:**
- `relay/db/models.py`: Alert, Assignment, Snooze models + AlertType enum
- `alembic/versions/0003_plan3_sla.py`: creates alerts/assignments/snoozes tables, RLS + FORCE RLS on all three
- `relay/sla/alerts.py`: build_alert_blocks() — Block Kit DM card with account/tier/waiting/SLA/4 action buttons
- `relay/sla/poller.py`: relay.poll_sla Celery Beat task (60s). Cross-tenant scan, snooze check, 5-min dedup, OOO skip, SLA policy lookup, bot token decrypt, DM send, Alert record, next_alert_at advance
- `relay/worker/celery_app.py`: beat_schedule wired for poll_sla
- `relay/slack/actions.py`: @app.action handlers for relay_claim_question, relay_snooze_1h, relay_snooze_4h, relay_mark_not_question
- `relay/slack/app.py`: imports actions module for registration
- `tests/test_sla_alerts.py`: 15 tests (alert card structure, action ids, escalation note, SLA states)
- `tests/test_slack_actions.py`: 9 tests (ack behaviour, UUID guard, question-not-found, snooze/claim/resolve)

Tests run: 100 passed, 2 skipped (DB integration without Postgres).

Open questions / TODOs:
- SAWarnings about SQLAlchemy relationship `overlaps` — cosmetic, pre-existing since PR #4
- Redis dedup on ingestion (idempotency key check before classify) — TODO stub in tasks.py
- HubSpot company upsert — still stubbed in hubspot_tasks.py
- CustomerAccount.name field guard in poller — defensive hasattr check

Next recommended step:
1. Codex: review and merge PRs #9, #10, #11 in order
2. Claude: start Plan 4 — source connectors (GitHub, Notion/Confluence) + retrieval pipeline

### Codex — 2026-06-05
Branch: `codex/plan-2-schema-pr4`, `codex/plan-2-hubspot`, `codex/plan-2-channel-registration`, `codex/handoff-2026-06-05`
Status: Plan 2 slices merged (PRs #4, #6, #7, #8). CI green on all.
Next: Review PRs #9, #10, #11 and merge in order. Start Plan 4 source connectors if Claude hasn't.
