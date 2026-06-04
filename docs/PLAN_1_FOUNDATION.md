# RELAY Plan 1: Classifier Validation + Foundation, Revised

## Summary
Build RELAY's first implementation slice: classifier validation tooling plus the production-grade foundation that later plans depend on. This plan creates the repo scaffold, offline/real classifier evaluation harness, async Slack/FastAPI foundation, encrypted token storage, PostgreSQL schema with RLS, Slack OAuth workspace install logic, Celery/Redis event queuing, App Home skeleton, and `/relay help`.

Important boundary:

> This plan may build foundation code, but no classifier-dependent product workflow should ship until the classifier validation gate is met.

## Locked Decisions
- Python 3.12 with `uv`.
- Async Slack Bolt + FastAPI.
- Slack Events API handlers must ack in under 3 seconds.
- Slack events are enqueued to Celery/Redis; classification happens in workers.
- Bolt/FastAPI/workers query Postgres directly.
- MCP is inference-only, never the DB/service bus.
- PostgreSQL RLS enforces tenant isolation.
- `Workspace.id` is internal UUID; `Workspace.slack_team_id` is Slack's team ID.
- Reinstall reuses the existing workspace row.
- v1 posts approved responses as bot, not as the CSM user.
- HubSpot account import moves into Plan 2.
- User-token posting, Salesforce, KMS, full deletion UI, and Marketplace docs are later plans.

## Tech Stack
- Python 3.12
- `uv`
- `slack-bolt[async]`
- FastAPI + Uvicorn
- SQLAlchemy 2 async + asyncpg
- Alembic
- PostgreSQL 15+
- Redis 7
- Celery 5
- `cryptography`
- Anthropic SDK
- Pydantic Settings v2
- pytest + pytest-asyncio
- httpx

## File Map
```text
relay/
├── pyproject.toml
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── classifier/
│   ├── __init__.py
│   ├── label.py
│   ├── classify.py
│   └── evaluate.py
├── relay/
│   ├── __init__.py
│   ├── config.py
│   ├── crypto.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   └── session.py
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── oauth.py
│   │   ├── verify.py
│   │   └── home.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   └── tasks.py
│   └── commands/
│       ├── __init__.py
│       └── help.py
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_crypto.py
    ├── test_models.py
    ├── test_oauth.py
    ├── test_rls.py
    ├── test_verify.py
    ├── test_worker.py
    ├── test_commands.py
    └── classifier/
        ├── __init__.py
        ├── fixtures/
        │   └── sample_labeled.jsonl
        ├── test_label_format.py
        ├── test_classify.py
        └── test_evaluate.py
```

## Task 0: Project Scaffolding
Create:
- `pyproject.toml`
- `.env.example`
- `alembic.ini`
- package directories

`pyproject.toml` dependencies:

```toml
[project]
name = "relay"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "slack-bolt[async]>=1.21",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pgvector>=0.3",
    "celery[redis]>=5.4",
    "redis>=5.2",
    "cryptography>=43",
    "anthropic>=0.40",
    "pydantic-settings>=2.7",
    "httpx>=0.28",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`.env.example`:

```bash
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=

DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test
REDIS_URL=redis://localhost:6379/0

TOKEN_ENCRYPTION_KEY=

ANTHROPIC_API_KEY=
CLASSIFIER_MODEL=
CLASSIFIER_OPEN_THRESHOLD=0.85
CLASSIFIER_CANDIDATE_THRESHOLD=0.60
CLASSIFIER_VARIANT=a

APP_BASE_URL=https://your-app.example.com
ENVIRONMENT=development
```

Acceptance:
- `uv sync` succeeds.
- Directory structure exists.
- `.env` and local caches are ignored by git.

## Task 1: Classifier Labeling Tool
Create:
- `classifier/label.py`
- `tests/classifier/fixtures/sample_labeled.jsonl`
- `tests/classifier/test_label_format.py`

Behavior:
- CLI reads raw JSONL messages.
- User labels each as `1` question/requires response or `0` no response needed.
- Output is labeled JSONL with `text` and `label`.
- Fixture contains at least 10 realistic support-channel examples.

Acceptance:
- `uv run pytest tests/classifier/test_label_format.py -v` passes.
- Label format is strict enough for evaluation scripts.

## Task 2: Classifier Prompt Variants
Create:
- `classifier/classify.py`
- `tests/classifier/test_classify.py`

Implementation:
- Provide two prompt variants: explicit rules and role-based classifier.
- Return structured `ClassificationResult`:
  - `is_question`
  - `confidence`
  - `reasoning`
  - `variant`
- Model name comes from `CLASSIFIER_MODEL`, not a hardcoded source constant.
- Add a safe default only in config, with comments telling the implementer to use a current available Haiku-class model.

Testing requirement:
- Unit tests must mock the Anthropic client.
- Unit tests must not require `ANTHROPIC_API_KEY`.
- Real model calls happen only through `classifier/evaluate.py`.

Acceptance:
- Tests prove obvious question and non-question outputs.
- Tests prove parsing handles valid JSON.
- Tests do not touch the network.

## Task 3: Classifier Evaluation + Threshold Sweep
Create:
- `classifier/evaluate.py`
- `tests/classifier/test_evaluate.py`

Implementation:
- Compute precision, recall, and F1 at a threshold.
- Sweep thresholds from 0.50 to 0.95, always including 0.60 and 0.85.
- Evaluation command runs real model calls against a labeled JSONL dataset.
- Misclassified examples are printed with truth, prediction, confidence, text excerpt, and reasoning.

Validation gate:
- Start with synthetic/anonymized Slack Connect-style data.
- Before any classifier-dependent product flow ships, collect pilot-labeled real messages where possible.
- Initial quality gate:
  - Precision >= 0.80
  - Recall >= 0.70
  - P95 time from event receipt to open-question creation target remains <= 5 minutes in later async flow
- If neither prompt variant passes, revise prompts and rerun.

Commit wording:
- Do not use "GATE PASSED" in commit messages unless the gate actually passed on the target dataset.
- Use `feat(classifier): evaluation script with threshold sweep` for the code.
- Record validated thresholds in a separate note or commit only after validation.

Acceptance:
- Unit tests pass without network.
- Evaluation command works with real `ANTHROPIC_API_KEY`.
- Thresholds are treated as hypotheses until validation output exists.

## Task 4: Config Module
Create:
- `relay/config.py`
- `tests/test_config.py`

Settings:
- Slack client ID/secret/signing secret.
- Optional dev bot token.
- Database URLs.
- Redis URL.
- Token encryption key.
- Anthropic API key.
- `classifier_model`.
- Classifier thresholds and variant.
- App base URL.
- Environment.

Validation:
- `TOKEN_ENCRYPTION_KEY` must be exactly 64 hex chars.
- `token_encryption_key_bytes` returns 32 bytes.
- Thresholds must be between 0 and 1.
- Open threshold must be >= candidate threshold.

Acceptance:
- Config tests cover valid env, bad key length, non-hex key, and invalid threshold ordering.

## Task 5: Crypto Module
Create:
- `relay/crypto.py`
- `tests/test_crypto.py`

Implementation:
- AES-256-GCM token encryption.
- 12-byte random nonce per encryption.
- Return ciphertext and nonce.
- Wrong key and tampered ciphertext raise hard errors.

Production note:
- Environment master key is acceptable for Plan 1/local beta foundation.
- Track explicit follow-up to replace with KMS/envelope encryption before Marketplace/public production:
  - KEK in cloud KMS.
  - Per-workspace DEK.
  - Rotation process.
  - Emergency revocation procedure.

Acceptance:
- Round-trip works.
- Ciphertext differs from plaintext.
- Nonce is unique.
- Wrong key fails.
- Tampering fails.

## Task 6: Database Engine + RLS Session Helper
Create:
- `relay/db/engine.py`
- `relay/db/session.py`
- `tests/conftest.py`

Implementation:
- Async SQLAlchemy engine.
- Async session factory.
- Session helper accepts optional `workspace_id`.
- When provided, session sets `app.current_workspace_id`.
- Tenant queries must run inside a workspace-scoped session once RLS tables exist.

Acceptance:
- Test fixtures use a real PostgreSQL test database.
- Tests run transactionally and clean up after themselves.

## Task 7: Database Models
Create:
- `relay/db/models.py`
- `tests/test_models.py`

Initial models:
- `Workspace`
- `WorkspaceToken`
- `WorkspaceSettings`
- `SlaPolicy`
- `User`
- `ClassificationFeedback`
- `AuditLog`

Model requirements:
- `Workspace.id` internal UUID primary key.
- `Workspace.slack_team_id` unique Slack team ID.
- Workspace reinstall uses `slack_team_id`.
- All tenant tables include `workspace_id`.
- `WorkspaceSettings` stores classifier thresholds and variant.
- `SlaPolicy` stores tier windows, not hardcoded app constants.
- `ClassificationFeedback` captures correction action, corrected label, original label/confidence.
- `AuditLog` includes:
  - `workspace_id`
  - actor user ID
  - actor Slack user ID
  - actor IP
  - user agent
  - event type
  - entity type
  - entity ID
  - old value
  - new value
  - timestamp

Do not include:
- `questions` table yet.
- `monitored_channels` table yet.
- fake indexes for future tables.

Acceptance:
- Model shape tests pass.
- All tenant-scoped models expose `workspace_id`.

## Task 8: Alembic Migration With RLS
Create:
- `alembic/env.py`
- `alembic/versions/0001_initial_schema.py`

Implementation:
- Generate migration from models.
- Add RLS policies for all tenant tables in this migration.
- Do not add placeholder SQL for tables that do not exist.
- Do not include `if False else "SELECT 1"` or similar fake migration logic.

RLS policy:
- Use `workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid` or equivalent safe expression.
- Ensure unset workspace context returns no tenant rows rather than leaking data.
- Add policies for:
  - workspace tokens
  - workspace settings
  - SLA policies
  - users
  - classification feedback
  - audit log

Audit enforcement:
- If roles are available, implement insert-only audit privileges in migration.
- If app DB roles are not yet formalized, state clearly in migration comments that append-only enforcement is deferred to the deployment-role plan.
- Do not claim append-only is enforced unless the migration actually enforces it.

Acceptance:
- Migration applies to dev database.
- Migration applies to test database.
- No fake future-table SQL exists.

## Task 9: RLS Isolation Tests
Create:
- `tests/test_rls.py`

Tests:
- With `app.current_workspace_id` set to workspace A, tenant queries do not return workspace B rows.
- With no workspace context set, tenant queries return no rows.
- Workspace table itself remains queryable by install/upsert code as needed.
- Audit log policy behavior is tested according to what the migration actually enforces.

Acceptance:
- RLS tests prove isolation behavior, not just schema presence.

## Task 10: Slack Request Signature Verification
Create:
- `relay/slack/verify.py`
- `tests/test_verify.py`

Implementation:
- Verify Slack HMAC-SHA256 signature.
- Reject stale timestamps older than 5 minutes.
- Reject future timestamps beyond tolerance.
- Reject malformed timestamps.
- Use constant-time comparison.
- Never log secret/signature/body.

Acceptance:
- Valid signature passes.
- Invalid signature fails.
- Stale/future/non-numeric timestamps fail.

## Task 11: Async Event Queue
Create:
- `relay/worker/celery_app.py`
- `relay/worker/tasks.py`
- `tests/test_worker.py`

Implementation:
- Celery app uses Redis broker/backend.
- JSON serialization only.
- `process_slack_event` task exists as a stub for Plan 2.
- Dedup key uses:
  - Slack team ID
  - channel ID
  - Slack message timestamp

Queue payload policy:
- Pass minimal event payloads in Redis.
- Later plans should prefer storing sensitive/full content in Postgres and passing IDs through the queue.

Acceptance:
- Task is registered.
- Dedup key is deterministic.
- Dedup key changes when timestamp changes.

## Task 12: Slack OAuth Install + Token Storage
Create:
- `relay/slack/oauth.py`
- `tests/test_oauth.py`

Implementation:
- `upsert_workspace_from_install`
  - Creates workspace on first install.
  - Reuses workspace on reinstall.
  - Updates Slack team name.
  - Clears `uninstalled_at`.
  - Seeds default workspace settings.
  - Seeds default SLA policies:
    - enterprise: 30 min response, 45 min escalation
    - pro: 120 min response, 180 min escalation
    - starter: 480 min response, 600 min escalation
- `store_bot_token`
  - Encrypts token.
  - Stores nonce.
  - Revokes active previous bot token.
  - Stores scopes.

Acceptance:
- New install creates workspace.
- Reinstall is idempotent.
- Default SLA policies are seeded.
- Token ciphertext is not plaintext.
- Old token is revoked when new token is stored.

## Task 13: Bolt App + FastAPI Mount
Create:
- `relay/slack/app.py`
- `relay/slack/home.py`
- `relay/api/main.py`

Implementation:
- Slack Bolt async app initialized.
- FastAPI exposes:
  - `/health`
  - `/slack/events`
  - `/slack/install`
  - `/slack/oauth_redirect`
- App Home skeleton shows:
  - RELAY welcome
  - setup checklist
  - placeholder admin-console button

Important note:
- Slack event handler registration that performs real processing belongs in Plan 2.
- No synchronous LLM calls or connector calls in request handlers.

Acceptance:
- `uvicorn relay.api.main:api --port 3000` starts.
- `GET /health` returns service health JSON.

## Task 14: `/relay help` Command
Create:
- `relay/commands/help.py`
- `tests/test_commands.py`

Behavior:
- `/relay` and `/relay help` ack and respond ephemerally.
- Unknown subcommands respond with a helpful error.
- Help text lists future commands but makes clear only help is active in Plan 1.

Acceptance:
- Handler acks once.
- Responds with Block Kit.
- Unknown subcommand includes provided subcommand in response.

## Task 15: Full Suite + Coverage
Run:
- Full unit suite.
- Coverage on critical modules.

Coverage targets:
- `relay/crypto.py`: >= 95%
- `relay/slack/verify.py`: >= 95%
- `relay/slack/oauth.py`: >= 80%
- `classifier/evaluate.py`: >= 90%

Acceptance:
- All tests pass.
- Critical coverage targets pass.
- No network calls occur in unit tests.
- Real Anthropic calls are isolated to explicit evaluation command.

## Self-Review Checklist
Before marking Plan 1 complete:
- Classifier evaluation tooling exists.
- Unit tests do not require real LLM credentials.
- Slack ack architecture is async-first.
- MCP is not in the DB/application path.
- `Workspace.id` and `Workspace.slack_team_id` are distinct.
- RLS is implemented and tested.
- Token encryption works.
- KMS migration is tracked as a follow-up.
- Fake future-table migration placeholders are absent.
- Audit enforcement claims match actual migration behavior.
- HubSpot is explicitly moved into Plan 2.
- No classifier-dependent product flow exists before validation.

## Subsequent Plans
### Plan 2: HubSpot + Account Registry + Channel Registration
- HubSpot OAuth.
- Normalized CRM account import.
- Account owner/tier/SLA mapping.
- Manual overrides.
- `/relay register`.
- `monitored_channels`.
- Store `customer_workspace_id`/external Slack team identifiers where available.
- Full async Slack event ingestion.
- `messages` and `questions` tables.
- 5-state question machine.

### Plan 3: SLA Engine + Alerts
- 60-second polling worker with `next_alert_at`.
- `alerts`, assignments, snoozes.
- DM alert cards.
- Claim, snooze, assign, mark not question.
- OOO, backup escalation, quiet hours.
- Auto-ack toggle.

### Plan 4: Source Connectors + Retrieval
- Connector interface.
- Docs connector.
- GitHub connector.
- Embedding pipeline.
- pgvector with `workspace_id`, `embedding_model`, `embedding_dims`.
- Tenant-safe retrieval.
- Source allowlists.

### Plan 5: Evidence Bundle + Draft Approval
- Context assembly.
- Prompt-injection defenses.
- Strict citations.
- Draft modal.
- Bot-posted approved response.
- Feedback and draft analytics.

### Plan 6: Resolution Memory + Account Pulse
- `/relay ask`.
- Resolution indexing.
- Review ignored messages.
- Account pulse.
- Impact metrics.

### Plan 7: Marketplace Readiness
- Landing page.
- Privacy policy.
- Sub-processor disclosure.
- Scope justification.
- `/relay delete-workspace-data`.
- Data retention controls.
- KMS/envelope encryption migration.
- Reviewer sandbox.
