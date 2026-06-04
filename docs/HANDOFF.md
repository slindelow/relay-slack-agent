# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`. Two open PRs: #1 `codex/repo-setup` (collaboration docs + Plan 1 overview) and #2 `claude/prd-update` (PRD v2 + detailed Plan 1 with code). PR #1 reviewed and approved by Claude — recommended merge order: #1 first, then #2. No code exists yet; Phase 0 classifier validation is the next work item.

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

## Agent Updates

### Codex — 2026-06-04
Branch: codex/repo-setup → PR #1
Status: Collaboration docs committed and pushed. PR #1 open.
Commits: `bd0be81`, `3222361`
Tests run: none
Open questions: GitHub CLI auth stale in Codex shell.
Next recommended step: Merge PR #1 after Claude review, then start `codex/plan-1-foundation`.

### Claude — 2026-06-04
Branch: claude/prd-update → PR #2
Status: Full revised PRD v2.0 committed (RELAY_PRD.md). Detailed implementation Plan 1 with code at docs/superpowers/plans/2026-06-04-relay-plan1-foundation.md. PR #1 reviewed and approved with comments (5 suggestions, none blocking). Recommended merge order: PR #1 first, PR #2 second.
Commits: `4407a85 docs: revised PRD (v2.0), Plan 1 implementation details, HANDOFF update`
Tests run: none (no code exists yet)
Open questions: After both PRs merge — should Phase 0 classifier validation start on `claude/classifier-validation` or `codex/plan-1-foundation`? Recommend Claude takes Phase 0 (offline Python tooling, no Slack integration) while Codex takes Phase 1 scaffolding in parallel.
Next recommended step: Merge PR #1 → merge PR #2 → Claude opens `claude/classifier-validation` for Phase 0 → Codex opens `codex/plan-1-foundation` for scaffold + crypto + config.
