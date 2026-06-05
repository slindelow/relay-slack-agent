# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`. PRs #1, #2, and #3 are merged. Plan 1 foundation is on `main`. Codex is implementing the first Plan 2 persistence slice on `codex/plan-2-foundation`.

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
Branch: codex/plan-1-foundation → PR #3 (MERGED)
Status: Plan 1 foundation merged to `main` at `055bfde`. GitHub Actions CI runs with a Postgres service and tests RLS under a non-superuser app role.
Commits: Plan 1 merged via PR #3.
Tests run: CI green on PR #3.
Open questions: none.
Next recommended step: Continue Plan 2 in small branches/PRs.

### Claude — 2026-06-04
Branch: codex/plan-1-foundation (same branch — added docs + tests)
Status: Added `README.md`, `tests/conftest.py`, `tests/test_oauth.py`, `tests/test_rls.py`. Also added `FORCE ROW LEVEL SECURITY` to migration and test fixtures (prevents bypass by table owner). Fixed README classifier CLI invocation to match actual positional-arg signature.
Commits: `ec074aa` docs+test · `2acf9c4` fix FORCE RLS
Tests run: 37 pass, 14 skip (integration tests need Postgres — skip gracefully without it).
Open questions: Plan 2 scope — channel registration and question machine. No blockers.
Next recommended step: Merge PR #3 → open `codex/plan-2-hubspot` for HubSpot OAuth + account import + channel registration + question machine.

### Codex — 2026-06-05
Branch: codex/plan-2-foundation
Status: First Plan 2 persistence slice in progress. Added/reconciled ORM models and migration for `crm_connections`, `customer_accounts`, `monitored_channels`, `messages`, `questions`, and `question_events`; added new tenant tables to RLS fixture coverage and model/RLS tests. Kuhn second-agent review recommended keeping this PR persistence-only and avoiding HubSpot/Slack workflow code until the DB contract lands.
Commits: `cbddc9a` ORM models · `c28fb44` model tests · `554f164` migration · `b86f61b` test fix · current reconciliation pending commit.
Tests run: `/Users/sofialindelow/.local/bin/uv run pytest tests -v --tb=short` -> 47 passed, 15 skipped; `/Users/sofialindelow/.local/bin/uv run alembic heads` -> `0002_plan2_schema`.
Open questions: none for schema slice; CI should validate Postgres-backed RLS tests after push.
Next recommended step: Push branch, open PR for Claude review focused on schema/RLS; after merge, split HubSpot OAuth and Slack channel registration into separate branches.
