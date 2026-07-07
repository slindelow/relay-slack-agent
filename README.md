# RELAY

RELAY is a Slack-native customer-success agent for teams managing Slack Connect customer channels. It detects unanswered customer questions, tracks SLA risk, retrieves context from CRM/docs/GitHub, drafts source-backed responses, and requires human approval before anything is posted back to a customer.

> **Current status as of 2026-07-02:** Railway is live and the core private-beta loop has been validated end-to-end in a real Slack Connect workspace: setup, channel monitoring, HubSpot sync, GitHub retrieval, Slack Search context, SLA alerts, draft review, and approved posting. RELAY is ready for hackathon submission and focused private-beta usage; it is not yet a self-serve public Slack Marketplace app.

**Demo video:** [Watch the RELAY walkthrough](https://youtu.be/vvf3aMxv6k8)

## Private Beta

> RELAY is currently in private beta. Install links are shared directly with invited CS teams.

**Install RELAY →** <https://web-production-acd3.up.railway.app/>

Once installed, four setup steps unlock the full feature set:

1. **Admin configured** — automatic on install (the person who clicks "Add to Slack" becomes admin)
2. **Add a customer channel** — run `/relay add #channel-name CompanyName enterprise @owner` for your first Slack Connect customer channel
3. **Connect HubSpot** — click "Connect HubSpot" in the RELAY App Home and complete OAuth
4. **Connect a knowledge source** — run `/relay setup` and connect GitHub

After the core setup steps, RELAY begins monitoring registered customer channels automatically. Slack Search is optional and adds permission-aware internal Slack context to drafts and `/relay ask`.

For a full walkthrough, see [docs/beta-user-guide.md](docs/beta-user-guide.md).
For deployment instructions, see [docs/deployment/private-beta-railway.md](docs/deployment/private-beta-railway.md).

---

## What Works Today

- Slack/FastAPI event surface for Slack OAuth, Events API, interactivity, App Home, and slash commands.
- `/relay help`, `/relay setup`, `/relay add`, `/relay ask`, `/relay pulse`, and `/relay delete-workspace-data` (with `settings`/`sources`/`connect` and `register` aliases).
- Slack slash commands must be run from the main message composer; Slack does not support slash commands in thread replies.
- Slack Connect channel registration and customer-team verification.
- Async worker ingestion, question classification, question state machine, SLA polling, DM alerts, claim/snooze/not-a-question actions.
- Source connector, embedding, retrieval, evidence bundle, draft generation, review modal, approved posting, impact metrics, feedback export, and resolution memory.
- Tenant isolation through PostgreSQL RLS and encrypted workspace/connector/CRM tokens.
- Marketplace-readiness foundation: deletion flows, public legal pages, scope justification, reviewer sandbox, Sentry/health hooks, and security hardening.

## Submission Notes

- **Best demo path:** register one Slack Connect channel, sync HubSpot and GitHub, ask a customer question, claim it, review the cited draft, and send the approved reply.
- **Slack app config:** before reinstalling or recording, run `scripts/configure-manifest.sh $APP_BASE_URL` and upload the generated manifest so Messages Tab, channel events, OAuth redirects, and scopes stay aligned.
- **Post-deploy smoke checks:** run `.venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live`, `.venv/bin/python scripts/smoke_kms.py`, and `curl $APP_BASE_URL/health` from an operator shell with beta env vars.
- **Known product follow-ups:** direct Google OAuth for Drive/Docs, richer admin/team management, and a denser multi-account dashboard. Google Drive connector internals exist in the repo, but the Slack setup UI is intentionally hidden until direct OAuth is production-ready.

## Private Beta Launch Docs

- Railway deployment runbook: `docs/deployment/private-beta-railway.md`
- AWS hardening runbook: `docs/deployment/private-beta-aws.md`
- End-to-end validation checklist: `docs/deployment/private-beta-acceptance.md`
- Non-technical user guide for CS admins: `docs/beta-user-guide.md`
- Slack app manifest: `slack-app-manifest.yaml`
- Local dev quickstart: `scripts/start-local.sh`
- Marketplace reviewer docs: `docs/marketplace/`
- Historical planning/status docs: `docs/HANDOFF.md`, `tasks/STATUS.md`, and `docs/PLAN_9_PRIVATE_BETA_LAUNCH.md`

## How It Works

1. A Slack admin installs RELAY into a workspace.
2. An admin registers a Slack Connect customer channel with `/relay add`.
3. A customer posts in the registered channel.
4. Slack sends the event to RELAY, and RELAY immediately acks Slack.
5. A Celery worker classifies the message and creates a question when appropriate.
6. The SLA poller alerts the account owner before the response window is missed.
7. A CSM claims the question, generates a cited draft, reviews it in Slack, and approves.
8. RELAY posts the approved response as the bot and stores useful resolution memory.

## Repository Layout

Top-level structure of this repository:

| Path | What lives here |
|------|-----------------|
| `relay/` | The application package. |
| `relay/api/` | FastAPI routes and the HTTP surface. |
| `relay/slack/` | Slack Bolt event handlers, commands, and interactive UI. |
| `relay/connectors/` | Knowledge-source connectors, chunking, embeddings, and semantic retrieval. |
| `relay/context/` | Evidence assembly and the MCP context server. |
| `relay/drafting/` | Cited draft generation, evidence bundling, and resolution memory. |
| `relay/question/`, `relay/sla/` | Question lifecycle and SLA tracking. |
| `relay/worker/` | Celery tasks (classification, drafting, sync). |
| `relay/db/` | SQLAlchemy models and session/RLS plumbing. |
| `classifier/` | Message classification logic and evaluation harness. |
| `alembic/` | Database migrations. |
| `docs/` | Architecture notes, runbooks, and the private-beta launch docs (including `docs/deployment/`). |
| `scripts/` | Operational and development scripts. |
| `tests/` | The pytest suite. |

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

For active work, use focused branches for larger changes and keep `main` deployable. After changing production behavior, run the pytest suite and redeploy the relevant Railway service.
