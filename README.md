# RELAY

RELAY is a Slack-native agent for customer success teams managing Slack Connect channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM and docs, drafts cited responses, and requires human approval before posting.

> **Current status:** Plan 1 (foundation) — classifier validation tooling, project scaffold, DB schema with RLS, token encryption, async Slack/FastAPI skeleton, and the `/relay help` command. No live classifier-dependent product flows exist yet.

---

## How it works

1. A customer posts in a shared Slack Connect channel.
2. The Slack Events API delivers the event to RELAY.
3. RELAY acks Slack in < 3 seconds, enqueues the event to Celery/Redis.
4. A worker classifies the message (question vs. no response needed).
5. If classified as an open question above the confidence threshold, RELAY opens a question record, starts the SLA timer, and alerts the owning CSM.
6. The CSM claims, drafts a response (with CRM/docs context retrieved), and approves.
7. RELAY posts the approved response as the bot and resolves the question.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12, uv |
| Slack | Bolt (async) |
| API | FastAPI + Uvicorn |
| DB | PostgreSQL 15+ (SQLAlchemy 2 async + asyncpg) |
| Migrations | Alembic |
| Queue | Celery 5 + Redis 7 |
| Classifier | Anthropic SDK (claude-3-5-haiku-* by default) |
| Token encryption | AES-256-GCM (cryptography) |
| Settings | Pydantic Settings v2 |
| Tests | pytest + pytest-asyncio |

---

## Quick start

### Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv)
- PostgreSQL 15+
- Redis 7

### Install dependencies

```bash
uv sync
```

### Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `SLACK_CLIENT_ID` | From your Slack app's Basic Information page |
| `SLACK_CLIENT_SECRET` | From your Slack app's Basic Information page |
| `SLACK_SIGNING_SECRET` | From your Slack app's Basic Information page |
| `DATABASE_URL` | Postgres async URL (`postgresql+asyncpg://...`) |
| `TOKEN_ENCRYPTION_KEY` | Exactly 64 hex chars (32 bytes). Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `APP_BASE_URL` | Public HTTPS URL (used for Slack OAuth redirect) |

### Set up the database

```bash
# Create the relay database and user
psql -U postgres -c "CREATE USER relay WITH PASSWORD 'relay';"
psql -U postgres -c "CREATE DATABASE relay OWNER relay;"
psql -U postgres -c "CREATE DATABASE relay_test OWNER relay;"

# Run migrations
uv run alembic upgrade head
```

### Start the server

```bash
uv run uvicorn relay.api.main:api --port 3000 --reload
```

Health check:

```bash
curl http://localhost:3000/health
# {"status":"ok","service":"relay"}
```

---

## Running tests

### Unit tests (no external services required)

```bash
uv run pytest tests/ -v
```

All unit tests pass without a running database, Redis, or Anthropic API key.

### Integration tests (requires PostgreSQL)

Set `TEST_DATABASE_URL` in `.env` and ensure the test DB exists:

```bash
psql -U postgres -c "CREATE DATABASE relay_test OWNER relay;"
uv run pytest tests/test_oauth.py tests/test_rls.py -v
```

Integration tests are skipped automatically when PostgreSQL is not reachable.

### Classifier evaluation (requires Anthropic API key)

```bash
uv run python -m classifier.evaluate tests/classifier/fixtures/sample_labeled.jsonl a
```

This runs real model calls. Do not ship classifier-dependent product flows until the validation gate passes (precision >= 0.80, recall >= 0.70) on the target dataset.

### Coverage

```bash
uv run pytest tests/ --cov=relay --cov=classifier --cov-report=term-missing
```

Coverage targets: `relay/crypto.py` ≥ 95 %, `relay/slack/verify.py` ≥ 95 %, `relay/slack/oauth.py` ≥ 80 %, `classifier/evaluate.py` ≥ 90 %.

---

## Project structure

```
relay/
├── classifier/          # Offline classifier tooling (label, classify, evaluate)
├── relay/
│   ├── config.py        # Pydantic Settings — all config in one place
│   ├── crypto.py        # AES-256-GCM token encryption
│   ├── db/
│   │   ├── engine.py    # Async SQLAlchemy engine
│   │   ├── models.py    # ORM models (Workspace, tokens, settings, SLA, users, audit)
│   │   └── session.py   # Session factory with optional RLS workspace context
│   ├── slack/
│   │   ├── app.py       # Bolt AsyncApp initialisation
│   │   ├── home.py      # App Home Block Kit skeleton
│   │   ├── oauth.py     # Workspace install / reinstall + token storage
│   │   └── verify.py    # HMAC-SHA256 Slack signature verification
│   ├── api/
│   │   └── main.py      # FastAPI app with /health and Bolt routes
│   ├── worker/
│   │   ├── celery_app.py  # Celery + Redis config
│   │   └── tasks.py       # process_slack_event stub
│   └── commands/
│       └── help.py      # /relay and /relay help handler
├── alembic/
│   └── versions/
│       └── 0001_initial_schema.py  # Schema + RLS policies for all tenant tables
└── tests/
    ├── conftest.py           # DB integration fixtures
    ├── test_config.py
    ├── test_crypto.py
    ├── test_models.py
    ├── test_oauth.py         # Integration: workspace install + token storage
    ├── test_rls.py           # Integration: RLS tenant isolation
    ├── test_verify.py
    ├── test_worker.py
    ├── test_commands.py
    └── classifier/
        ├── fixtures/
        │   └── sample_labeled.jsonl
        ├── test_label_format.py
        ├── test_classify.py
        └── test_evaluate.py
```

---

## Architecture decisions

**Ack in < 3 s.** Slack requires an HTTP 200 within 3 seconds. All LLM, CRM, and retrieval work runs in Celery workers — never in the request handler.

**RLS for tenant isolation.** Every tenant table has a PostgreSQL row-level security policy keyed on `app.current_workspace_id`. The session helper sets this local variable before any tenant query. An unset context returns zero rows.

**Idempotency key.** `{team_id}:{channel_id}:{message_ts}` deduplicates Slack event deliveries in the Celery queue.

**Token encryption.** Bot tokens are encrypted with AES-256-GCM before storage. The master key lives in `TOKEN_ENCRYPTION_KEY`. A KMS/envelope-encryption migration is tracked for Marketplace readiness (Plan 7).

**`Workspace.id` vs `Workspace.slack_team_id`.** The internal UUID (`id`) is the FK target for all tenant tables. Slack's team ID (`slack_team_id`) is a unique natural key used for install/reinstall upserts only.

**MCP is inference-only.** Bolt/FastAPI/workers query Postgres directly. MCP is never in the application or database path.

---

## Development workflow

This repo uses a two-agent development model:

- **Codex** (`codex/...` branches) — implements features.
- **Claude** (`claude/...` branches) — reviews, plans, classifies.

Neither agent commits directly to `main`. Both update `docs/HANDOFF.md` at the end of each session. See `docs/CLAUDE_OPERATING_BRIEF.md` for the full operating brief.

---

## Roadmap

| Plan | Focus |
|------|-------|
| 1 (current) | Classifier validation, scaffold, DB, crypto, Slack skeleton |
| 2 | HubSpot OAuth, account import, channel registration, question machine |
| 3 | SLA engine, 60 s polling, DM alerts, claim/snooze/assign |
| 4 | Source connectors (docs, GitHub), embedding pipeline, pgvector retrieval |
| 5 | Evidence bundle, draft approval modal, bot-posted response |
| 6 | Resolution memory, account pulse, `/relay ask` |
| 7 | Marketplace readiness, KMS encryption, privacy policy, data deletion |
