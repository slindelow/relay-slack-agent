# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo initialized and pushed to GitHub at `https://github.com/slindelow/relay-slack-agent`. Collaboration docs are committed on `codex/repo-setup`; Claude's PRD update work is on `claude/prd-update`.

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

## Latest Agent Update
Date: 2026-06-04
Agent: Codex
Branch: codex/repo-setup
Status: Baseline `main` commit created; collaboration docs committed and pushed on setup branch. Remote repository exists.
Commits: `bd0be81 chore: initialize relay planning repo`; current branch commit `docs: add multi-agent collaboration handoff`
Tests run: none
Open questions: GitHub CLI auth still reports a stale invalid token in Codex shell, so PR creation may need browser/manual flow.
Next recommended step: Open PRs for `codex/repo-setup` and `claude/prd-update` into `main`, then start Plan 1 implementation from a fresh `codex/plan-1-foundation` branch after review.
