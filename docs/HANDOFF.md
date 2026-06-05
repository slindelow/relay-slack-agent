# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`. PRs #1–#3 merged (Plan 1 on `main`). Plan 2 fully implemented on `claude/plan-2-foundation` — **PR #5 open, ready to merge.**

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
- **Commit incrementally** — after each completed file or logical chunk, not in one end-of-session batch.

## Agent Updates

### Claude — 2026-06-05
Branch: claude/plan-2-foundation → **PR #5 (OPEN, ready to merge)**
Status: Full Plan 2 implemented. 75 unit tests pass, 17 DB integration tests skip without Postgres (pass in CI).
Commits (summary): Plan 2 ORM models + Alembic migration 0002 + RLS · HubSpot OAuth client, routes, Celery task · Channel registration helper + /relay register command · Question state machine (open/claim/resolve/expire + QuestionEvent) · Async Slack message event ingestion (Bolt handler + Celery worker classify + Question creation)
Tests run: 75 passed, 17 skipped.
Open questions: SAWarnings about ORM relationship overlaps — non-blocking, cosmetic.
Next recommended step: Merge PR #5 → open `codex/plan-3-sla` for Plan 3 (60s polling SLA worker, alert DMs, claim/snooze/assign).

### Codex — 2026-06-04/05
Branch: codex/plan-2-foundation / codex/plan-2-schema (stale — superseded by claude/plan-2-foundation)
Status: Schema slice work done, superseded by Claude's comprehensive Plan 2 branch.
Next: After PR #5 merges, start Plan 3 on a fresh `codex/plan-3-sla` branch.

### Codex — 2026-06-04 (Plan 1)
Branch: codex/plan-1-foundation → PR #3 (MERGED to main at `055bfde`)
Status: Plan 1 foundation merged. CI green.
