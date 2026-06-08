# RELAY

RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts source-backed responses, and requires human approval before anything is posted back to a customer.

> **Current status as of 2026-06-08:** Plans 1-8 have built most of the backend product loop and security foundation. Plan 9 is now active: private beta launch, deployment, Slack distribution, onboarding UX, production KMS, live Slack Connect validation, and external-user packaging. RELAY is not yet a self-serve public Slack Marketplace app.

## Private Beta

> RELAY is currently in private beta. Install links are shared directly with invited CS teams.

**Install RELAY →** `https://your-relay-app.example.com/` *(replace with your deployed APP_BASE_URL)*

Once installed, four setup steps unlock the full feature set:

1. **Admin configured** — automatic on install (the person who clicks "Add to Slack" becomes admin)
2. **Register a channel** — run `/relay register #channel-name CompanyName` in your first customer channel
3. **Connect HubSpot** — click "Connect HubSpot" in the RELAY App Home and complete OAuth
4. **Connect a knowledge source** — run `/relay settings` and connect GitHub or Google Drive

After all four steps, the App Home shows ":tada: Setup complete" and RELAY begins monitoring for unanswered customer questions automatically.

For a full walkthrough, see [docs/beta-user-guide.md](docs/beta-user-guide.md).
For deployment instructions, see [docs/deployment/private-beta-aws.md](docs/deployment/private-beta-aws.md).

---

## What Works Today

- Slack/FastAPI event surface for Slack OAuth, Events API, interactivity, App Home, and slash commands.
- `/relay help`, `/relay settings`, `/relay register`, `/relay ask`, `/relay pulse`, and `/relay delete-workspace-data`.
- Slack Connect channel registration and customer-team verification.
- Async worker ingestion, question classification, question state machine, SLA polling, DM alerts, claim/snooze/not-a-question actions.
- Source connector, embedding, retrieval, evidence bundle, draft generation, review modal, approved posting, impact metrics, feedback export, and resolution memory.
- Tenant isolation through PostgreSQL RLS and encrypted workspace/connector/CRM tokens.
- Marketplace-readiness foundation: deletion flows, public legal pages, scope justification, reviewer sandbox, Sentry/health hooks, and security hardening.

## What Still Blocks Private Beta

- Production deployment must be stood up for web, worker, beat, Postgres with pgvector, Redis, secrets, health checks, and monitoring.
- Slack app configuration must be created from `slack-app-manifest.yaml` and pointed at the deployed `APP_BASE_URL`.
- Admin onboarding has beta setup/status surfaces; full OAuth-based connector setup remains post-beta polish.
- HubSpot company/account upsert has an initial implementation and still needs beta validation against real HubSpot data.
- AWS KMS provider selection is implemented and still needs IAM/config smoke validation before live customer secrets use it.
- A real Slack Connect end-to-end beta flow still needs to be validated before external users rely on RELAY.

## Private Beta Launch Docs

- Active shared plan: `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md`
- AWS deployment runbook: `docs/deployment/private-beta-aws.md`
- Slack app manifest: `slack-app-manifest.yaml`
- Marketplace reviewer docs: `docs/marketplace/`
- Multi-agent handoff/status: `docs/HANDOFF.md` and `tasks/STATUS.md`

## How It Works

1. A Slack admin installs RELAY into a workspace.
2. An admin registers a Slack Connect customer channel with `/relay register`.
3. A customer posts in the registered channel.
4. Slack sends the event to RELAY, and RELAY immediately acks Slack.
5. A Celery worker classifies the message and creates a question when appropriate.
6. The SLA poller alerts the account owner before the response window is missed.
7. A CSM claims the question, generates a cited draft, reviews it in Slack, and approves.
8. RELAY posts the approved response as the bot and stores useful resolution memory.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12, uv |
| Slack | Bolt async |
| API | FastAPI + Uvicorn |
| DB | PostgreSQL 15+ with pgvector, SQLAlchemy 2 async, asyncpg |
| Migrations | Alembic |
| Queue | Celery 5 + Redis 7 |
| LLM | Anthropic SDK |
| Embeddings | Voyage or OpenAI |
| Token encryption | AES-256-GCM with Plan 9 AWS KMS production path |
| Settings | Pydantic Settings v2 |
| Tests | pytest + pytest-asyncio |

## Local Development

### Prerequisites

- Python 3.12
- `uv`
- PostgreSQL 15+ with pgvector for integration tests
- Redis 7 for local worker/scheduler testing

### Install

```bash
uv sync
cp .env.example .env
```

Fill in the required settings in `.env`, especially:

```bash
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=
DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay
REDIS_URL=redis://localhost:6379/0
TOKEN_ENCRYPTION_KEY=
ANTHROPIC_API_KEY=
APP_BASE_URL=http://localhost:3000
```

Generate `TOKEN_ENCRYPTION_KEY` with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Database

```bash
psql -U postgres -c "CREATE USER relay WITH PASSWORD 'relay';"
psql -U postgres -c "CREATE DATABASE relay OWNER relay;"
psql -U postgres -c "CREATE DATABASE relay_test OWNER relay;"
uv run alembic upgrade head
```

### Run Locally

```bash
uv run uvicorn relay.api.main:api --port 3000 --reload
uv run celery -A relay.worker.celery_app.celery worker --loglevel=INFO
uv run celery -A relay.worker.celery_app.celery beat --loglevel=INFO
```

Health check:

```bash
curl http://localhost:3000/health
```

Private beta install page:

```bash
open http://localhost:3000/
```

## Tests

```bash
uv run pytest -q
```

Integration tests that need PostgreSQL are skipped automatically when `TEST_DATABASE_URL` is unavailable.

Classifier validation requires a real Anthropic API key:

```bash
uv run python -m classifier.evaluate tests/classifier/fixtures/sample_labeled.jsonl a
```

Do not rely on classifier-driven alerts for beta until the target dataset reaches precision >= 0.80 and recall >= 0.70, or thresholds are adjusted and documented.

## Collaboration Workflow

This repo uses a two-agent development model:

- Codex branches use `codex/...`
- Claude branches use `claude/...`
- Neither agent commits directly to `main`
- Both agents check and update `docs/HANDOFF.md`
- Plan 9 is the active plan until the private beta launch blockers are cleared
