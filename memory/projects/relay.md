# RELAY Project Memory

## Snapshot
RELAY is a Slack/FastAPI/Celery/Postgres app for customer-success teams managing Slack Connect channels. It ingests registered customer-channel messages, classifies customer questions, tracks SLA risk, retrieves account/docs/GitHub/Slack context, generates source-backed drafts with Anthropic, and posts only after human approval.

## Stack
- Python 3.12 with `uv`.
- FastAPI web app plus Slack Bolt async.
- Celery worker/beat with Redis.
- PostgreSQL with pgvector and RLS.
- Anthropic for classifier/drafts; Voyage or OpenAI for embeddings.
- Railway is the live beta deployment; AWS/KMS is the hardened target path.

## Live Status
- `main` is stable/live.
- Railway URL: `https://web-production-acd3.up.railway.app`.
- Core Slack loop validated live: customer question -> classify -> SLA alert -> claim -> MCP-powered draft -> review modal -> approved send -> resolved.
- HubSpot OAuth and account sync are live; `/relay pulse` can show ARR.
- Remaining beta checklist items: SLA timer verification, workspace deletion, uninstall.

## Latest Audit
Review log: `docs/CODEBASE_REVIEW_2026-06-30.md`.

Top risks to address:
- Authenticate/authorize `/mcp-api/mcp`.
- Replace forgeable HubSpot install identity query params with a signed/one-time browser token.
- Delete old knowledge chunks when a source document changes before re-embedding.
- Add real Slack event dedup before classifier calls.
- Avoid materializing full GitHub paginated lists before slicing.

## Validation Baseline
As of the 2026-06-30 audit:
- `uv run pytest -q` passed: 327 passed, 34 skipped, 1 warning.
- `uv run python -m compileall -q relay tests classifier` passed.
- `git diff --check` passed.
