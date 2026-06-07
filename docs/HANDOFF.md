# RELAY Multi-Agent Handoff

## Project
RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts cited responses, and requires human approval before posting.

## Current Status
Repo live at `https://github.com/slindelow/relay-slack-agent`.

Merged to `main` (Plans 1 + 2 foundation):
- PR #1: collaboration docs
- PR #2: PRD v2.0 + Plan 1 details
- PR #3: Plan 1 foundation scaffold (classifier, DB, crypto, Slack, Celery)
- PR #4: Plan 2 core schema + migration 0002 + RLS on 6 tenant tables
- PR #6: HubSpot OAuth client, routes, encrypted connection storage, sync stub
- PR #7: DB-backed `/relay register`, customer account/channel registration
- PR #8: HANDOFF update

Open PRs (pending merge, in dependency order):
- PR #9 (`claude/plan-2-question-machine`): 5-state question machine, 10 unit tests
- PR #10 (`claude/plan-2-event-ingestion`): Bolt message handler + full Celery classify worker, 5 unit tests
- PR #11 (`claude/plan-3-sla`): Full SLA engine — see below

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
- Commit incrementally — after each completed file or logical chunk.

## Agent Updates

### Codex — 2026-06-07 (Plan 7 workspace deletion flow)
Branch: `codex/plan-7-marketplace-readiness`
Status: US-002 mostly implemented locally. Full suite green: 220 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added migration `0007_plan7_deletion.py` and ORM model `WorkspaceDeletionJob` for deletion job status tracking.
- Added `relay.worker.deletion_tasks.delete_workspace_data`, with explicit dependency-order deletes, final `audit_log` entry, workspace row deletion, and failed-job marking.
- Added `/relay delete-workspace-data` confirmation modal and confirmation handler that creates a job and enqueues deletion.
- Added Slack `app_uninstalled` handler that revokes active workspace tokens and enqueues the same deletion task.
- Registered deletion tasks with Celery and updated `/relay help` routing/copy.
- Added focused unit tests for modal construction, job creation, delete-order guarantees, and message event enqueue behavior.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_delete_command.py tests/test_deletion_tasks.py tests/test_slack_events.py tests/test_models.py -q` — 29 passed.
- `.venv/bin/python -m pytest -q` — 220 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic upgrade head --sql` — rendered through `0007_plan7_deletion`.
- `git diff --check` — passed.

Remaining for US-002:
- Add a live DB functional test that creates a full data tree, runs deletion, and verifies rows are gone.

Next recommended Plan 7 steps:
1. Connector-level purge.
2. KMS envelope encryption.
3. Reviewer sandbox seed and walkthrough.

### Codex — 2026-06-07 (Plan 7 marketplace readiness start)
Branch: `codex/plan-7-marketplace-readiness` stacked on `claude/plan-6-feedback-memory`
Status: Plan 6 draft PR #14 is open. Plan 7 started with reviewer-visible pages, scope documentation, and monitoring health. Full suite green: 214 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added optional Sentry initialization in `relay/api/main.py`, controlled by `SENTRY_DSN`; startup remains silent when unset.
- Extended `/health` to check database and Redis dependencies and return 503 when either is down.
- Added unauthenticated `/privacy`, `/terms`, and `/sub-processors` HTML pages for Slack Marketplace review.
- Added `docs/marketplace/scope-justification.md` covering each required Slack scope and confirming optional connector scopes.
- Added tests for healthy/degraded health responses and public legal pages.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_api.py tests/test_config.py -q` — 7 passed, 1 warning.
- `.venv/bin/python -m pytest -q` — 214 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `git diff --check` — passed.

Next recommended Plan 7 steps:
1. Workspace deletion flow (`/relay delete-workspace-data` + Celery job tracking).
2. Connector-level purge.
3. KMS envelope encryption.
4. Reviewer sandbox seed and walkthrough.

### Codex — 2026-06-06 (Plan 6 `/relay pulse`)
Branch: `claude/plan-6-feedback-memory`
Status: US-008 complete. Plan 6 implementation is complete on this branch. Full suite green: 209 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added `/relay pulse [account-name]` handler with no-arg top account summary and named-account detailed pulse.
- Summary shows top accounts by open question count with tier, ARR, renewal proximity, and owner/backup context.
- Detail view shows open questions, 30-day SLA met rate, last resolved question date, renewal, tier, ARR, and backup owner when the primary owner is OOO.
- Registered pulse routing in `/relay` and updated help copy.
- Added unit coverage for summary blocks, detail blocks, not-found behavior, and handler summary response.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_pulse_command.py -q` — 5 passed.
- `.venv/bin/python -m pytest -q` — 209 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `git diff --check` — passed.

Next recommended step:
1. Do a final Plan 6 review pass, then open/merge PR for `claude/plan-6-feedback-memory`.
2. Start Plan 7 marketplace readiness after Plan 6 lands.

### Codex — 2026-06-06 (Plan 6 feedback export endpoint)
Branch: `claude/plan-6-feedback-memory`
Status: US-007 complete. Full suite green: 204 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added `GET /relay/admin/feedback-export` returning workspace-scoped feedback signals as `application/x-ndjson`.
- Authenticates `Authorization: Bearer <token>` through Slack `auth.test`, resolves workspace by `team_id`, and requires local `User.relay_role == "admin"`.
- Supports `?days=` with max 90-day clamp and sets an attachment filename.
- Added unit tests for non-admin 403 and admin JSONL output.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_feedback_export.py tests/test_api.py -q` — 3 passed, 1 warning.
- `.venv/bin/python -m pytest -q` — 204 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `git diff --check` — passed.

Next recommended Plan 6 step:
1. Add `/relay pulse` account digest (US-008).

### Codex — 2026-06-06 (Plan 6 App Home accuracy review)
Branch: `claude/plan-6-feedback-memory`
Status: US-006 complete. Full suite green: 202 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added App Home `Accuracy` section fed by rolling 7-day `FeedbackSignal` rows and total question count.
- Renders `mark_not_question` correction count, classification accuracy, no-corrections empty state, and an `Export feedback` link button.
- `publish_app_home` now queries tenant-scoped feedback rows and question counts, and builds the export URL from `APP_BASE_URL`.
- Added unit coverage for no-correction and populated accuracy states.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_home.py -q` — 10 passed.
- `.venv/bin/python -m pytest -q` — 202 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `git diff --check` — passed.

Next recommended Plan 6 steps:
1. Add admin feedback export endpoint (US-007).
2. Add `/relay pulse` account digest (US-008).

### Codex — 2026-06-06 (Plan 6 App Home impact metrics)
Branch: `claude/plan-6-feedback-memory`
Status: US-005 complete. Full suite green: 200 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Added App Home `Impact` section fed by rolling 30-day `ImpactMetric` rows.
- `build_home()` now accepts `impact_rows` and renders SLA met rate, draft accepted rate, median time to send, and total questions handled.
- `publish_app_home` queries tenant-scoped impact metrics for the installed Slack workspace and degrades gracefully if unavailable.
- Added unit coverage for empty-state and populated impact metrics rendering.

Tests/verification:
- `.venv/bin/python -m pytest tests/test_home.py -q` — 8 passed.
- `.venv/bin/python -m pytest -q` — 200 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `git diff --check` — passed.

Next recommended Plan 6 steps:
1. Build App Home accuracy/feedback review (US-006).
2. Add admin feedback export endpoint (US-007).
3. Add `/relay pulse` account digest (US-008).

### Codex — 2026-06-06 (Plan 6 review + memory/ask slice)
Branch: `claude/plan-6-feedback-memory`
Status: Plan 5 is merged on `origin/main`; this branch is Plan 6 work on top of it. Full suite green: 193 passed, 19 skipped, 1 pre-existing Starlette/httpx deprecation warning.

Work completed:
- Reviewed Claude's Plan 6 US-001 migration/model work. Fixed the `KnowledgeEntry` ORM metadata to match the migration's tenant-scoped composite FK (`workspace_id`, `question_id`) and restored the migration after a single-column FK drift. Removed composite `ON DELETE SET NULL` on the knowledge-chunk-to-entry FK because `workspace_id` is non-null.
- Added `relay/drafting/memory.py` with `index_approved_response()`: creates `KnowledgeEntry`, summarizes with Haiku behind a safe fallback, and embeds the approved Q+A as a `KnowledgeChunk` with `knowledge_entry_id`.
- Wired `relay_send_draft` to index approved/sent responses after `ImpactMetric` write.
- Extended `embed_chunks()` with a keyword-only `knowledge_entry_id` path and validation that a chunk belongs to either a source document or a memory entry, not both.
- Updated retrieval so memory chunks cite as `provider="relay_memory"`, increment `KnowledgeEntry.reuse_count`, and win ties against docs at equal semantic distance.
- Added `/relay ask <question>` handler and top-level `/relay` routing. It resolves workspace by Slack team, runs tenant-scoped retrieval, and returns ephemeral Block Kit source results.

Tests/verification:
- `.venv/bin/python -m pytest -q` — 193 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic heads` — `0006_plan6_memory (head)`.
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic upgrade head --sql` — renders through Plan 6.

Next recommended Plan 6 steps:
1. Build App Home impact metrics section (US-005).
2. Build App Home accuracy/feedback review (US-006).
3. Add admin feedback export endpoint (US-007).
4. Add `/relay pulse` account digest (US-008).

### Claude — 2026-06-05 (Plans 4 + 5 — connectors, drafting, approval)
Branch (Plan 4): `claude/plan-4-connectors-v2` → **merged to main as PR #12**
Branch (Plan 5): `claude/plan-5-clean` → PR #13 open, CI pending
Status: Plans 1–4 in main. 184 tests pass, 0 failures.

**Plan 4 session work:**
- Fixed PR #11 (SLA) CI: conftest env defaults + TENANT_TABLES cleanup; rebased onto merged #9/#10; merged.
- Created `claude/plan-4-connectors-v2` from clean main; cherry-picked Plan 4 commit (37 files, 9 US); updated `uv.lock` for new deps; fixed CI to use `pgvector/pgvector:pg15` + `CREATE EXTENSION IF NOT EXISTS vector` in fixture.
- PR #12 merged: source connectors, embedding pipeline, semantic retrieval.

**Plan 5 built (PR #13 — `claude/plan-5-clean`):**

**US-001** — Migration `0005_plan5_drafts.py`: `drafts`, `feedback_signals`, `impact_metrics` tables + `account_context` JSONB on `customer_accounts`. FK from `retrieval_logs.draft_id` → `drafts.id`. ORM models `Draft`, `DraftStatus`, `FeedbackSignal`, `ImpactMetric` in `relay/db/models.py`.

**US-002** — `relay/drafting/evidence.py`: `assemble_evidence()`. Joins Question + Message, retrieves chunks, deduplicates by provider+url, reranks by authority tier + freshness, 8k-token budget enforcement.

**US-003** — `relay/drafting/generator.py`: `generate_draft()`. Claude Sonnet `submit_draft` tool_use; all retrieved content in `<retrieved_source trust="external">` XML delimiters; retries once on schema mismatch; `requires_human_review` always True; saves Draft row.

**US-004** — `relay/worker/drafting_tasks.py`: `generate_draft_for_question` Celery task. Checks `claimed` state, assembles evidence, generates draft, DMs CSM on success/failure.

**US-005** — `relay/slack/draft_modal.py`: pure `build_draft_modal()`. Question excerpt, CRM context (tier/ARR/renewal), internal brief, confidence badge (high/medium/low), editable plain_text_input (max 3000 chars), source citations with stale warnings, Regenerate + Discard action buttons.

**US-006** — `relay_send_draft` view_submission handler: posts to customer channel with CSM attribution, resolves question, writes QuestionEvent + ImpactMetric.

**US-007** — `relay_discard_draft` + `relay_regenerate_draft` action handlers: log FeedbackSignal (discard_draft/regenerate_draft), update draft status, enqueue regen task.

**US-008** — `relay_generate_draft` App Home button + `build_home()` extended with `questions_needing_draft` section. `relay.worker.drafting_tasks` in Celery include list.

**prd.json** advanced to Plan 6 (8 stories: knowledge_entries, index_approved_response, relay_memory retrieval citation, /relay ask, App Home impact/accuracy sections, admin JSONL export, /relay pulse).

Tests: 184 passed, 0 failures, 19 skipped.

Next for next agent:
1. Wait for PR #13 CI (should pass — pgvector fix is in main now)
2. Merge PR #13
3. Create `claude/plan-6-feedback-memory` from new main; implement 8 Plan 6 stories from `prd.json`

### Claude — 2026-06-05 (Plan 4 — source connectors + embedding pipeline)
Branch: `claude/plan-3-sla` (Plan 4 code stacked on Plan 3 pending merge)
Status: All 9 Plan 4 user stories complete. 137 tests pass, 0 failures, 0 warnings.

**What was built:**

**US-001** — pgvector migration `0004_plan4_connectors.py` + ORM models (`SourceConnector`, `SourceDocument`, `KnowledgeChunk`, `RetrievalLog`) — already complete from prior session; `config` JSONB column added to `source_documents` for GitHub citation metadata.

**US-002** — `relay/connectors/` package: abstract `Connector` base class (abc), `get_connector()` lazy registry (avoids circular imports), `ConnectorType` enum in models.

**US-003** — `relay/connectors/embeddings.py`: `embed_chunks()` + `_get_embeddings()`. Supports `voyage-3` (default) and `text-embedding-3-small` via `EMBEDDING_PROVIDER` env var. Idempotent: skips chunks with matching `content_hash` already in DB. Batch size 20.

**US-004** — `relay/connectors/chunking.py`: `chunk_text()` using `tiktoken` `cl100k_base`. Token-aware overlap. Graceful fallback if tiktoken not installed (whitespace tokenizer for tests).

**US-005** — `relay/connectors/google_drive.py`: `GoogleDriveConnector`. Decrypts credentials from `source_connectors.encrypted_credentials`, exports Drive files as plain text, content-hash dedup, chunks+embeds, updates `source_documents`.

**US-006** — `relay/connectors/github.py`: `GitHubConnector`. Syncs issues, PRs, releases, selected markdown files. `citation()` returns `{title, url, status, labels, updated_at, stale}` where stale = last_synced_at > 48h.

**US-007** — `relay/connectors/retrieval.py`: `retrieve()`. Embeds query, runs `ORDER BY embedding <=> CAST(:vec AS vector)` scoped to `workspace_id`, writes `retrieval_logs` row on every call.

**US-008** — `relay/worker/connector_tasks.py`: `sync_connector` + `sync_all_connectors` Celery tasks. Beat schedule: every 6h. `sync_connector` sets `sync_status='error'` on exception without propagating (one failing connector doesn't block others).

**US-009** — `relay/slack/home.py`: `build_home(connector_rows)` — pure block builder, no DB calls. `publish_app_home` handler loads connectors from DB and passes them to builder. Staleness warning if `last_synced_at > 24h`.

**New dependencies added** (pyproject.toml + installed): `tiktoken>=0.7`, `voyageai>=0.3`, `openai>=1.30`, `PyGithub>=2.3`, `google-api-python-client>=2.130`, `google-auth>=2.29`, `google-auth-oauthlib>=1.2`.

**New config fields**: `embedding_provider`, `voyage_api_key`, `openai_api_key`, `google_drive_credentials_json`, `github_token` (all default to `""` so existing tests pass).

Tests run: 137 passed, 0 failures, 19 skipped (integration, need live DB), 1 warning (pre-existing FastAPI httpx deprecation).

Next recommended steps:
1. Merge PRs #9, #10, #11 in order → clean Plan 3 baseline on main
2. Open PR for Plan 4 from `claude/plan-3-sla` (or create a dedicated `claude/plan-4-connectors` branch rebased on main after the merges)
3. Start Plan 5 — convert `tasks/prd-plan5-drafting-approval.md` to active `prd.json`

### Codex — 2026-06-05 (Plan 4 storage foundation)
Branch: `claude/plan-3-sla` working tree
Status: Started Plan 4 with the source connector storage layer. Added migration `0004_plan4_connectors.py` and ORM models for `SourceConnector`, `SourceDocument`, `KnowledgeChunk`, and `RetrievalLog`. The migration enables pgvector, creates `vector(1536)` embeddings with an ivfflat cosine index, applies RLS to all four new tenant tables, and uses same-workspace composite FKs for connector/document/chunk ownership.

Also tightened review/test hygiene:
- Centralized minimal test env defaults in `tests/conftest.py` so Slack app modules import deterministically.
- Added Plan 3 RLS coverage for `alerts`, `assignments`, and `snoozes`.
- Updated `/relay help` text to match implemented/planned command status.
- Updated `docs/CLAUDE_OPERATING_BRIEF.md` with the first-principles review approach requested by the user.
- Fixed Alembic env config to read the ini section without configparser interpolation before overriding `sqlalchemy.url` from `DATABASE_URL`.

Tests run:
- `.venv/bin/python -m pytest -q` — 103 passed, 19 skipped, 1 warning.
- `.venv/bin/python -m compileall -q relay alembic tests` — passed.
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic heads` — single head: `0004_plan4_connectors`.
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic upgrade head --sql` — offline SQL renders through Plan 4.

Not run:
- `alembic upgrade head` against a live Postgres+pgvector database; local DB is not configured/reachable in this environment.

Open notes:
- `tasks/` planning docs are useful as the durable task breakdown; `prd.json` and `progress.txt` duplicate that state and should only be kept if an automation needs them.
- Plan 3 docs mention assign, but this checkout has only the `Assignment` model, not an assignment Slack action.

Next recommended step:
1. Run `alembic upgrade head` against a real Postgres database with pgvector available.
2. Continue Plan 4 US-002: connector interface + lazy registry, then chunking and embedding pipeline.

### Claude — 2026-06-05 (session 3, code review)
Branch: `claude/plan-3-sla` → **PR #11 (OPEN, updated)**
Status: Full structural code review completed on Plans 2 + 3. 34 tests pass, 0 warnings.

**Bugs fixed in this session:**

1. **Critical — poller detached-object bug** (`relay/sla/poller.py`):
   The cross-tenant scan closed its session before `_alert_question` ran.
   Question was detached — `next_alert_at`, `alert_count`, `last_alert_at` mutations
   never persisted. Fixed by splitting into Phase 1 (SELECT id+workspace_id only,
   no session state needed) + Phase 2 (load Question inside the workspace-scoped
   session so all mutations commit atomically).

2. **Race condition — double-claim** (`relay/question/machine.py`):
   `_load_question` used a plain SELECT. Two concurrent Bolt handlers could both
   read state="open" and both claim. Fixed with `.with_for_update()`.

3. **Dead code** (`relay/sla/alerts.py`):
   `deadline_secs` on line 51 computed via complex ternary then immediately
   discarded (line 53 recomputed it). Simplified to clean two-branch conditional.

4. **Missing label check** (`relay/worker/tasks.py` on `claude/plan-2-event-ingestion`):
   Classifier confidence was checked without verifying `is_question`. A
   high-confidence "not a question" would create a spurious Question row. Fixed
   by gating all Question creation under `if result_cls.is_question`.

5. **SAWarnings eliminated** (`relay/db/models.py`):
   All 15 pre-existing SAWarning overlaps on composite-FK relationships silenced
   with `overlaps=` annotations throughout the model graph.

Tests run: 34 passed, 0 warnings (unit tests; DB integration tests skipped).

Open TODOs (non-blocking):
- Redis dedup on ingestion (idempotency key check before classify)
- HubSpot company upsert — still stubbed in hubspot_tasks.py
- `Question.snoozed_until` field is dead schema — set nowhere, read by nothing
  (Snooze table is authoritative); remove in a future migration

Next recommended step:
1. Codex: review and merge PRs #9, #10, #11 in order
2. Claude: start Plan 4 — source connectors (GitHub, Notion/Confluence) + retrieval pipeline

### Codex — 2026-06-05
Branch: `codex/plan-2-schema-pr4`, `codex/plan-2-hubspot`, `codex/plan-2-channel-registration`, `codex/handoff-2026-06-05`
Status: Plan 2 slices merged (PRs #4, #6, #7, #8). CI green on all.
Next: Review PRs #9, #10, #11 and merge in order. Start Plan 4 source connectors if Claude hasn't.

### Codex — 2026-06-05 (Plan 4 foundation pass)
Branch: `claude/plan-4-connectors-clean`
Status: Plan 4 connector runtime reviewed and hardened, then Plan 5 draft foundation started. Connector sync now targets a specific `connector_id` end to end instead of re-querying by provider type; the worker owns visible `syncing` / `synced` / `error` transitions around provider work; chunking rejects invalid overlap settings that could hang; retrieval rejects empty queries and invalid `top_k` values before embedding. Added draft storage (`0005_plan5_drafts.py`, `Draft`, `DraftStatus`) and a narrow `relay.drafts.generator` service that stores pending drafts, ties retrieval logs to draft ids, blocks customer-facing drafts when no verified evidence is retrieved, and parses mocked Anthropic draft JSON.

Working standard updated in `docs/CLAUDE_OPERATING_BRIEF.md`: future review/problem work should inspect the current full state before advancing, keep code/context surface minimal, prefer structural root-cause repairs over bandaids, verify generated output, and split work only when scopes are independent.

Tests run:
- `.venv/bin/python -m pytest tests/test_draft_generator.py tests/test_retrieval.py tests/test_models.py -q` — 29 passed
- `.venv/bin/python -m pytest tests/test_connector_tasks.py tests/test_github_connector.py tests/test_google_drive_connector.py tests/test_chunking.py tests/test_retrieval.py tests/test_models.py -q` — 45 passed
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic heads` — `0005_plan5_drafts (head)`
- `DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay .venv/bin/python -m alembic upgrade head --sql` — rendered 608 lines including draft table, draft RLS, and retrieval-log-to-draft FK
- `.venv/bin/python -m pytest -q` — 154 passed, 19 skipped, 1 warning
- `.venv/bin/python -m compileall relay alembic` — passed

Open notes:
- Slack task tools were not exposed by the current tool surface after discovery; available organization tooling here is Codex thread automation and explicitly authorized sub-agents.
- Next product step is Slack human approval: surface pending drafts with evidence citations, support edit/approve/discard actions, and bot-post approved responses with attribution.
