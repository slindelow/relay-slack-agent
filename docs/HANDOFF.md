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
Status: Full Plan 1 foundation implemented and pushed. PR #3 open against main.
Commits: `54c8f29` feat(plan-1) scaffold · `ec074aa` + `2acf9c4` README/integration tests
Tests run: `uv run pytest tests/ -q` → 37 passed, 14 skipped (DB integration skips without Postgres).
Open questions: none — PR ready for review.
Next recommended step: Claude reviews PR #3, approves or comments; merge to main; open Plan 2 branch.

### Claude — 2026-06-04
Branch: codex/plan-1-foundation (same branch — added docs + tests)
Status: Added `README.md`, `tests/conftest.py`, `tests/test_oauth.py`, `tests/test_rls.py`. Also added `FORCE ROW LEVEL SECURITY` to migration and test fixtures (prevents bypass by table owner). Fixed README classifier CLI invocation to match actual positional-arg signature.
Commits: `ec074aa` docs+test · `2acf9c4` fix FORCE RLS
Tests run: 37 pass, 14 skip (integration tests need Postgres — skip gracefully without it).
Open questions: Plan 2 scope — channel registration and question machine. No blockers.
Next recommended step: Merge PR #3 → open `codex/plan-2-hubspot` for HubSpot OAuth + account import + channel registration + question machine.
