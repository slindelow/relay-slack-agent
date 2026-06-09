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

## RDS PostgreSQL Configuration

1. Create a DB parameter group based on `postgres15`.
2. Set `shared_preload_libraries = vector` (required for pgvector).
3. After the instance is running, connect and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   This is also handled automatically by `alembic upgrade head` if the migration includes `CREATE EXTENSION IF NOT EXISTS vector` (verify in `alembic/versions/`).
4. Recommended instance class for beta: `db.t4g.medium` (2 vCPU, 4 GiB RAM).
5. Multi-AZ: optional for beta, required for production.

## ECS Fargate Task Definitions

All three services share one container image. Recommended settings per task:

| Service | CPU | Memory | Command |
|---------|-----|--------|---------|
| web | 512 | 1024 MiB | `uv run uvicorn relay.api.main:api --host 0.0.0.0 --port 3000` |
| worker | 1024 | 2048 MiB | `uv run celery -A relay.worker.celery_app worker -Q default --loglevel=info` |
| beat | 256 | 512 MiB | `uv run celery -A relay.worker.celery_app beat --loglevel=info` |

**Health check for the web task:**
```json
{
  "command": ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"],
  "interval": 30,
  "timeout": 5,
  "retries": 3,
  "startPeriod": 60
}
```

**ALB health check:** path `/health`, expected HTTP 200.

## Secrets Manager Key Names

Store secrets under a prefix, e.g. `/relay/beta/`. Each key is a plain string unless noted.

| Secrets Manager path | Maps to env var |
|---------------------|----------------|
| `/relay/beta/SLACK_CLIENT_ID` | `SLACK_CLIENT_ID` |
| `/relay/beta/SLACK_CLIENT_SECRET` | `SLACK_CLIENT_SECRET` |
| `/relay/beta/SLACK_SIGNING_SECRET` | `SLACK_SIGNING_SECRET` |
| `/relay/beta/DATABASE_URL` | `DATABASE_URL` (asyncpg URI) |
| `/relay/beta/TOKEN_ENCRYPTION_KEY` | `TOKEN_ENCRYPTION_KEY` (64 hex chars) |
| `/relay/beta/ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` |
| `/relay/beta/HUBSPOT_CLIENT_ID` | `HUBSPOT_CLIENT_ID` |
| `/relay/beta/HUBSPOT_CLIENT_SECRET` | `HUBSPOT_CLIENT_SECRET` |
| `/relay/beta/ERASURE_SECRET` | `ERASURE_SECRET` |
| `/relay/beta/VOYAGE_API_KEY` | `VOYAGE_API_KEY` |
| `/relay/beta/SENTRY_DSN` | `SENTRY_DSN` |

Non-secret env vars (`APP_BASE_URL`, `ENVIRONMENT`, `KMS_PROVIDER`, `KMS_KEY_ID`, model names) can be set directly in the ECS task definition as environment variables.

Reference secrets from the task definition:
```json
{
  "secrets": [
    {
      "name": "SLACK_CLIENT_SECRET",
      "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:/relay/beta/SLACK_CLIENT_SECRET"
    }
  ]
}
```

## Deployment Steps

1. Build and publish the container image from the repository root:
   ```bash
   docker build -t relay:latest .
   docker tag relay:latest ACCOUNT.dkr.ecr.REGION.amazonaws.com/relay:latest
   docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/relay:latest
   ```
2. Provision RDS Postgres 15+ with pgvector (see RDS section above).
3. Provision ElastiCache Redis 7. Confirm the ECS security group can reach both.
4. Store secrets in Secrets Manager (see Secrets Manager key names above).
5. Run migrations (one-off ECS task or local with DB tunnel):
   ```bash
   uv run alembic upgrade head
   ```
6. Register task definitions for web, worker, beat and create ECS services.
7. Configure the Slack app using `slack-app-manifest.yaml`:
   ```bash
   scripts/configure-manifest.sh https://your-app-base-url.example.com
   ```
   Paste the generated manifest into https://api.slack.com/apps.
8. Run the operator preflight from a shell that has the beta env vars and deploy tooling. A local `.env.beta` file is safe to use because `.env.*` is git-ignored:
   ```bash
   .venv/bin/python scripts/beta_preflight.py --env-file .env.beta
   .venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live
   ```
   The first command checks env/tooling/manifest readiness. The `--live` command also calls `/health` and runs the KMS smoke.
9. Open `https://your-app-base-url.example.com/` and install the app into the beta Slack workspace.

## Smoke Checks

```bash
curl https://relay-beta.example.com/health
uv run celery -A relay.worker.celery_app.celery inspect ping --timeout=5
KMS_PROVIDER=aws KMS_KEY_ID=arn:aws:kms:... uv run python scripts/smoke_kms.py
.venv/bin/python scripts/beta_preflight.py --live
.venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live
```

Done means:
- `/health` returns `{"status":"ok","db":"ok","redis":"ok"}`.
- Celery reports at least one worker.
- KMS smoke prints `KMS smoke ok` using the beta KMS key.
- Beta preflight reports all required checks as `PASS`.
- `/relay help` works in the installed Slack workspace.
- App Home opens without errors.
- `/relay settings` shows setup state and links.

## AWS KMS IAM Permissions

The ECS task role that runs web, worker, beat, and one-off migration/smoke commands must be allowed to call these actions on the configured `KMS_KEY_ID`:

```json
{
  "Effect": "Allow",
  "Action": ["kms:Encrypt", "kms:Decrypt"],
  "Resource": "arn:aws:kms:REGION:ACCOUNT_ID:key/KEY_ID"
}
```

The smoke command uses a throwaway data encryption key and a fake token string. It does not read or write customer data.

## Current Beta Gaps

- AWS KMS provider selection is implemented, but the beta environment still needs IAM validation and a live KMS smoke check before real customer secrets are stored.
- HubSpot company upsert has an initial implementation and needs validation against real beta HubSpot data before CRM-backed account sync is considered beta-ready.
- Connector setup has beta Slack modals for GitHub tokens and Google Drive credential JSON. Full OAuth-based connector onboarding remains post-beta polish.
