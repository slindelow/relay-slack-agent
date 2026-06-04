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
Branch: codex/plan-1-foundation → PR #3 (open)
Status: Full Plan 1 foundation implemented and pushed. PR #3 open against main. GitHub Actions CI now runs with a Postgres service; latest work fixes asyncpg/Postgres tenant context setup and runs RLS integration tests as a non-superuser app role so CI cannot bypass RLS.
Commits: `54c8f29` feat(plan-1) scaffold · `ec074aa` + `2acf9c4` README/integration tests · `8ddfe56` + `39cb866` CI · `3343faa` integration fixture stabilization · `0da12a2` RLS context fix · current non-superuser RLS fixture fix pending commit.
Tests run: `/Users/sofialindelow/.local/bin/uv run pytest tests -v --tb=short` -> 38 passed, 14 skipped; critical coverage command passed locally, with OAuth coverage low because local Postgres-backed tests skipped.
Open questions: none — waiting on CI to confirm Postgres/RLS integration path.
Next recommended step: Push non-superuser RLS fixture fix, confirm CI green, then ask Claude to review PR #3 before merge.

### Claude — 2026-06-04
Branch: codex/plan-1-foundation (same branch — added docs + tests)
Status: Added `README.md`, `tests/conftest.py`, `tests/test_oauth.py`, `tests/test_rls.py`. Also added `FORCE ROW LEVEL SECURITY` to migration and test fixtures (prevents bypass by table owner). Fixed README classifier CLI invocation to match actual positional-arg signature.
Commits: `ec074aa` docs+test · `2acf9c4` fix FORCE RLS
Tests run: 37 pass, 14 skip (integration tests need Postgres — skip gracefully without it).
Open questions: Plan 2 scope — channel registration and question machine. No blockers.
Next recommended step: Merge PR #3 → open `codex/plan-2-hubspot` for HubSpot OAuth + account import + channel registration + question machine.
