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
- **Commit incrementally.** Commit after each completed file or logical unit of work — do not batch all changes into one end-of-session commit. Both Claude and Codex follow this rule.

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

## Engineering Review Standards

Before opening a PR, starting new work, or responding to a review/problem request, review the current branch with a senior-engineer posture:

- Read the source of truth first (`RELAY_PRD.md`, `docs/HANDOFF.md`, active plan docs, tests, and the changed code) before planning the next implementation step.
- Prefer the smallest coherent architecture over accumulated helpers. Remove duplication and dead paths when they obscure ownership or state flow.
- Optimize for operational efficiency: Slack handlers ack first, slow or external work goes to workers, Celery payloads stay JSON-serializable, and DB sessions stay scoped to the mutation they commit.
- Keep context lean. Use docs and tests as durable memory; avoid scattering scratch notes or repeating long rationale in code.
- Treat tests as architecture. A passing suite is not enough if new tenant tables, state transitions, or async boundaries are not represented in the harness.
- Treat generated output as part of the product. Render migrations, docs, dashboards, or UI artifacts when possible and repair the producing structure when output is wrong or bloated.
- Split work across tools or agents only when scopes are independent, ownership is clear, and integration cost is lower than local execution.

### Priority order
1. **Critical correctness**: session lifecycle bugs (detached ORM objects), race conditions (missing SELECT FOR UPDATE on state transitions), missing commits on mutation paths.
2. **Security**: unchecked classifier label vs. confidence, token handling, tenant boundary leaks.
3. **Dead code**: unused imports, unreachable computed values, shadow assignments.
4. **Warnings as signal**: SAWarnings from SQLAlchemy are architectural feedback — trace to root cause, fix with `overlaps=` annotations or `viewonly=True`, not silence with comments alone.
5. **Test coverage**: every public function with a state-dependent path needs a test for each valid and invalid transition.

### Fix approach (non-negotiable)
**No bandaid fixes.** When a bug is found:
1. Identify the structural root cause (e.g. detached object = wrong session scope).
2. Rebuild from first principles (e.g. load entity inside the session that will commit it).
3. The fix must eliminate the cause, not paper over the symptom.

Example: the SLA poller had a bug where Question attribute updates never persisted. The root cause was loading questions in a cross-tenant session that closed before per-tenant work began. The fix was to split into Phase 1 (scan: fetch IDs only) and Phase 2 (mutate: load Question inside workspace session so changes commit with it). Not: `session.merge(question)` as a patch.

### SQLAlchemy composite FK pattern
RELAY uses `(workspace_id, entity_id)` composite FKs for RLS enforcement. This causes SQLAlchemy to warn about `workspace_id` being writable via multiple relationship paths. Resolution:
- Add `overlaps="..."` annotations as directed by the warning message.
- All workspace_id values are set explicitly in constructors — we never rely on ORM cascade to propagate workspace_id through relationships.
