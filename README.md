# RELAY

RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts source-backed responses, and requires human approval before anything is posted back to a customer.

> **Current status as of 2026-06-25:** Plans 1-10 are merged. Railway is live and the core private-beta product loop has been validated end-to-end in a real Slack Connect workspace. RELAY is ready for focused beta follow-up, but is not yet a self-serve public Slack Marketplace app.

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
For deployment instructions, see [docs/deployment/private-beta-railway.md](docs/deployment/private-beta-railway.md).

---

## What Works Today

- Slack/FastAPI event surface for Slack OAuth, Events API, interactivity, App Home, and slash commands.
- `/relay help`, `/relay settings`, `/relay register`, `/relay ask`, `/relay pulse`, and `/relay delete-workspace-data`.
- Slack Connect channel registration and customer-team verification.
- Async worker ingestion, question classification, question state machine, SLA polling, DM alerts, claim/snooze/not-a-question actions.
- Source connector, embedding, retrieval, evidence bundle, draft generation, review modal, approved posting, impact metrics, feedback export, and resolution memory.
- Tenant isolation through PostgreSQL RLS and encrypted workspace/connector/CRM tokens.
- Marketplace-readiness foundation: deletion flows, public legal pages, scope justification, reviewer sandbox, Sentry/health hooks, and security hardening.

## What Still Blocks Broader Private Beta

The core loop works live. Remaining work before broader invited usage is validation and polish:

- **Finish remaining live validation** — HubSpot, setup-complete state, SLA timer, account pulse ARR, workspace deletion, and uninstall remain pending in `docs/deployment/beta-validation-checklist.md`.
- **Refresh Slack app config on each reinstall** — run `scripts/configure-manifest.sh $APP_BASE_URL` and upload the generated manifest so Messages Tab, channel events, OAuth redirects, and scopes stay aligned.
- **Run beta preflight/smokes after deploys** — from an operator shell with beta env vars, run `.venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live` and `.venv/bin/python scripts/smoke_kms.py`.
- **Keep HubSpot optional for core demos** — CRM-backed ARR and setup completion need HubSpot env vars/OAuth; GitHub-backed evidence and `/relay ask` already work.

## Private Beta Launch Docs

- Active shared plan: `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md`
- Railway deployment runbook: `docs/deployment/private-beta-railway.md`
- AWS hardening runbook: `docs/deployment/private-beta-aws.md`
- End-to-end validation checklist: `docs/deployment/private-beta-acceptance.md`
- Non-technical user guide for CS admins: `docs/beta-user-guide.md`
- Slack app manifest: `slack-app-manifest.yaml`
- Local dev quickstart: `scripts/start-local.sh`
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
| Token encryption | AES-256-GCM; Railway beta uses `TOKEN_ENCRYPTION_KEY`, AWS KMS remains the hardened production path |
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

## MCP Server

RELAY exposes a Model Context Protocol server that gives AI assistants (including Claude) governed access to RELAY's context tools. The server is automatically mounted at `/mcp` when the FastAPI app starts.

### Available Tools

| Tool name | Description |
|-----------|-------------|
| `question_lookup` | Fetch full context for a classified question (excerpt, urgency, account, channel) |
| `evidence_assembly` | Assemble a complete evidence bundle for a question (pgvector + CRM + Slack RTS) |
| `draft_generation` | Assemble evidence and generate a human-review-required customer draft (load-bearing path) |
| `get_question_context` | Low-level question context fetch |
| `get_account_context` | Low-level account context fetch |
| `search_indexed_knowledge` | Semantic search over indexed knowledge entries |
| `search_slack_context` | Permission-aware internal Slack search (requires user search token) |
| `assemble_evidence_for_question` | Full evidence bundle assembly |

### Start the MCP server (stdio mode, for `claude mcp` or MCP inspector)

```bash
uv run python -m relay.context.mcp_server
```

### MCP over HTTP (streamable HTTP transport — starts automatically with the FastAPI app)

```bash
uv run uvicorn relay.api.main:api --port 3000 --reload
# MCP endpoint: http://localhost:3000/mcp-api/mcp
```

Connect with MCP inspector:
```bash
npx @modelcontextprotocol/inspector http://localhost:3000/mcp-api/mcp
```

Production endpoint (Railway):
```
https://web-production-acd3.up.railway.app/mcp-api/mcp
```

Or add to Claude Code's MCP config (`~/.claude.json`):
```json
{
  "mcpServers": {
    "relay": {
      "command": "uv",
      "args": ["run", "python", "-m", "relay.context.mcp_server"],
      "cwd": "/path/to/relay"
    }
  }
}
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
