# Private Beta AWS Deployment Runbook

This runbook describes the target private-beta deployment for RELAY. It is intentionally AWS-oriented so the beta environment can evolve into the live product without reworking KMS, secrets, and observability.

## Target Topology

| Component | AWS target | Process |
| --- | --- | --- |
| Web/API | ECS Fargate service behind HTTPS load balancer | `uv run uvicorn relay.api.main:api --host 0.0.0.0 --port 3000` |
| Worker | ECS Fargate service | `uv run celery -A relay.worker.celery_app.celery worker --loglevel=INFO` |
| Scheduler | ECS Fargate service | `uv run celery -A relay.worker.celery_app.celery beat --loglevel=INFO` |
| Database | RDS PostgreSQL 15+ with pgvector | `DATABASE_URL=postgresql+asyncpg://...` |
| Queue/cache | ElastiCache Redis 7 | `REDIS_URL=redis://...` |
| Secrets | AWS Secrets Manager / ECS task secrets | Slack, Anthropic, HubSpot, connector, KMS config |
| Encryption | AWS KMS | `KMS_PROVIDER=aws`, `KMS_KEY_ID=...` |
| Errors | Sentry | `SENTRY_DSN=...` |
| Logs/metrics | CloudWatch + Sentry | service logs, health checks, worker checks |

## Required Environment

```bash
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=

DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...

TOKEN_ENCRYPTION_KEY= # 64 hex chars; legacy fallback until KMS migration is complete
KMS_PROVIDER=aws
KMS_KEY_ID=

ANTHROPIC_API_KEY=
CLASSIFIER_MODEL=claude-3-5-haiku-latest
DRAFT_MODEL=claude-3-5-sonnet-latest
SUMMARY_MODEL=claude-haiku-4-5-20251001

APP_BASE_URL=https://relay-beta.example.com
ENVIRONMENT=beta
SENTRY_DSN=

HUBSPOT_CLIENT_ID=
HUBSPOT_CLIENT_SECRET=
HUBSPOT_REDIRECT_URI=https://relay-beta.example.com/hubspot/oauth_redirect

EMBEDDING_PROVIDER=voyage
VOYAGE_API_KEY=
OPENAI_API_KEY=

ERASURE_SECRET=
```

## Deployment Steps

1. Build and publish the container image from the repository root.
2. Provision RDS Postgres with the `vector` extension available.
3. Provision Redis and confirm the ECS tasks can connect to it.
4. Store all required environment variables in Secrets Manager or ECS task secrets.
5. Run migrations:

```bash
uv run alembic upgrade head
```

6. Start the web, worker, and scheduler services.
7. Configure the Slack app using `slack-app-manifest.yaml`, replacing every `https://relay-beta.example.com` URL with `APP_BASE_URL`.
8. Open `https://relay-beta.example.com/` and install the app into the beta Slack workspace.

## Smoke Checks

```bash
curl https://relay-beta.example.com/health
uv run celery -A relay.worker.celery_app.celery inspect ping --timeout=5
```

Done means:
- `/health` returns `{"status":"ok","db":"ok","redis":"ok"}`.
- Celery reports at least one worker.
- `/relay help` works in the installed Slack workspace.
- App Home opens without errors.
- `/relay settings` shows setup state and links.

## Current Beta Gaps

- `KMS_PROVIDER=aws` must be fully enabled before live beta secrets are stored under AWS KMS.
- HubSpot company upsert must be completed before CRM-backed account sync is considered beta-ready.
- Connector setup needs admin-driven OAuth/configuration before non-engineers can self-serve Google Drive or GitHub.
