# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`. Plan 1 is merged. Plan 2 is being integrated in small PRs from Claude's broad source branch.

Merged Plan 2 slices:
- PR #4: core schema, migration, RLS coverage, tenant-scoped composite foreign keys.
- PR #6: HubSpot OAuth foundation, signed state, encrypted connection storage, sync stub.
- PR #7: DB-backed `/relay register`, customer account/channel registration, Slack Connect customer team capture.

Closed as superseded:
- PR #5: broad Claude Plan 2 branch. It remains useful as source material, but should not be merged directly because its schema and HubSpot portions have been extracted and hardened in smaller PRs.

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
- Use isolated git worktrees for active PR branches when multiple agents are working in the repo.

## Agent Updates

### Codex — 2026-06-05
Branch: `codex/plan-2-schema-pr4`, `codex/plan-2-hubspot`, `codex/plan-2-channel-registration`
Status: Integrated three Plan 2 slices through PRs #4, #6, and #7. Rawls reviewed the schema tenant-isolation fix and confirmed the P1 blocker was closed. Kuhn was asked to review HubSpot; no blocker returned before merge. PR #5 closed as superseded by smaller PRs.
Commits: merged via squash commits `91837e6` (schema/RLS), `c38e0c6` (HubSpot OAuth), `a9cae93` (channel registration).
Tests run: GitHub Actions CI green on PR #4, PR #6, and PR #7. Local worktree tests also passed for each slice; local Postgres-backed tests skipped where no local DB was available.
Open questions: SQLAlchemy composite-FK relationship overlap warnings remain non-blocking cleanup. HubSpot account upsert from companies is still stubbed. OAuth state is signed but not server-stored with TTL; acceptable for foundation, stronger replay protection is a follow-up.
Next recommended step: Extract Claude's question state machine slice into a clean branch from `main`, then async Slack event ingestion/classification worker as a separate branch.
