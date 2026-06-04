# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`. PR #1 (`codex/repo-setup`) and PR #2 (`claude/prd-update`) are merged. Codex has started Plan 1 foundation implementation on `codex/plan-1-foundation`.

## Source Of Truth
- `RELAY_PRD.md`
- `docs/PLAN_1_FOUNDATION.md`
- `docs/superpowers/plans/2026-06-04-relay-plan1-foundation.md`
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

## Agent Updates

### Codex — 2026-06-04
Branch: codex/plan-1-foundation
Status: Initial Plan 1 foundation implemented: project scaffold, classifier label/classify/evaluate tooling, config validation, AES-256-GCM crypto, SQLAlchemy models, Alembic initial migration with RLS policies, Slack signature verification, Celery task stub, Slack OAuth helpers, FastAPI/Bolt skeleton, App Home skeleton, and `/relay help`.
Commits: pending
Tests run: `$HOME/.local/bin/uv run pytest tests -v --tb=short` -> 37 passed; coverage run for `relay.crypto`, `relay.slack.verify`, and `classifier.evaluate` -> critical targets met.
Open questions: Need Claude review on whether Plan 1 should add real Postgres/RLS integration tests now or defer to the next hardening pass.
Next recommended step: Push `codex/plan-1-foundation`, open PR, and have Claude review security/RLS/test-depth before merge.

### Claude — 2026-06-04
Branch: claude/prd-update -> merged PR #2
Status: Full revised PRD v2.0 committed (`RELAY_PRD.md`) and merged. Detailed implementation Plan 1 with code at `docs/superpowers/plans/2026-06-04-relay-plan1-foundation.md`.
Commits: `4407a85 docs: revised PRD (v2.0), Plan 1 implementation details, HANDOFF update`
Tests run: none (planning/docs only)
Open questions: Should Claude open `claude/classifier-validation-review` as a critique branch, or review Codex's classifier/evaluation implementation directly in PR?
Next recommended step: Review Codex Plan 1 foundation PR with special focus on classifier validation integrity, RLS, token handling, and Slack ack architecture.
