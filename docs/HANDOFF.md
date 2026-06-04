# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo initialized locally. Collaboration docs are committed on `codex/repo-setup`. GitHub remote creation/push is blocked until GitHub CLI auth is refreshed.

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
Status: Baseline `main` commit created; collaboration docs committed on setup branch. GitHub CLI auth for `slindelow` is currently invalid.
Commits: `bd0be81 chore: initialize relay planning repo`; current branch commit `docs: add multi-agent collaboration handoff`
Tests run: none
Open questions: GitHub auth refresh is required before remote creation/push.
Next recommended step: Run `gh auth login -h github.com`, create GitHub remote, push `main` and `codex/repo-setup`, then open PR.
