# Claude Operating Brief for RELAY

## Role
You are collaborating with Codex on RELAY, a Slack-native customer-success agent for teams managing Slack Connect customer channels.

Your primary role is to review, pressure-test, and implement scoped branches without conflicting with Codex work.

## Product Summary
RELAY detects unanswered customer questions in Slack Connect channels, uses CRM/docs/GitHub context to understand account risk and technical truth, drafts source-backed responses, and requires human approval before posting.

## Source Of Truth
- Product PRD: `RELAY_PRD.md`
- Current build plan: `docs/PLAN_1_FOUNDATION.md`
- Shared project status: `docs/HANDOFF.md`
- Stable branch: `main`

## Collaboration Rules
- Never commit directly to `main`.
- Work on `claude/...` branches.
- Check `docs/HANDOFF.md` before starting.
- Check `git status` before editing.
- Pull/rebase latest `main` before starting a branch.
- Do not rewrite Codex commits.
- Do not edit files currently owned by an active Codex branch unless explicitly assigned.
- Keep PRs scoped and reviewable.
- Update `docs/HANDOFF.md` before ending a session.

## Branch Naming
Use:
- `claude/review-plan-1`
- `claude/classifier-validation-review`
- `claude/security-rls-review`
- `claude/docs-marketplace-review`

Codex branches use:
- `codex/...`

## Review Priorities
When reviewing Codex PRs, prioritize:
1. Functional correctness.
2. Slack 3-second ack safety.
3. Tenant isolation and RLS.
4. Token/security handling.
5. Classifier validation integrity.
6. Test coverage.
7. Marketplace/privacy risk.
8. Maintainability.

## Architecture Rules
Do not reverse these decisions:
- Slack request handlers ack immediately.
- LLM calls happen only in async workers or explicit evaluation scripts.
- Bolt/FastAPI/workers query Postgres directly.
- MCP is inference-only, not the DB or service bus.
- PostgreSQL RLS enforces tenant isolation.
- `Workspace.id` is internal UUID.
- `Workspace.slack_team_id` is Slack's team ID.
- v1 posts approved responses as bot.
- HubSpot is the first CRM provider.
- Salesforce is post-launch/next provider.

## Current Build Sequence
1. Plan 1: Classifier validation + foundation.
2. Plan 2: HubSpot + account registry + channel registration.
3. Plan 3: SLA engine + alerts.
4. Plan 4: Source connectors + retrieval.
5. Plan 5: Evidence bundle + draft approval.
6. Plan 6: Resolution memory + account pulse.
7. Plan 7: Marketplace readiness.

## Plan 1 Focus
Plan 1 includes:
- Project scaffold.
- Classifier labeling/evaluation tooling.
- Mocked classifier unit tests.
- Config module.
- AES-256-GCM token encryption.
- Async SQLAlchemy/Postgres foundation.
- RLS migration and isolation tests.
- Slack signature verification.
- Celery/Redis event queue.
- Slack OAuth workspace upsert/token storage.
- FastAPI/Bolt mount.
- App Home skeleton.
- `/relay help`.

## Handoff Format
When ending work, update `docs/HANDOFF.md` with:

```markdown
## Latest Agent Update
Date:
Agent:
Branch:
Status:
Commits:
Tests run:
Open questions:
Next recommended step:
```

## Definition Of Done For Any Branch
- Tests relevant to the change pass.
- No unrelated files changed.
- No secrets committed.
- `docs/HANDOFF.md` updated.
- PR description includes changes, tests, risks, and next steps.
