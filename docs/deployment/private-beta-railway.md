# Private Beta Railway Deployment Runbook

Railway is the current private-beta hosting path. AWS remains the hardened production/Marketplace path for AWS KMS and managed infrastructure review, but the first friendly beta should use Railway unless the team explicitly switches back.

## Target Topology

| Component | Railway target | Process |
| --- | --- | --- |
| Web/API | Railway web service from `Dockerfile` | `bash scripts/start_web.sh` |
| Database | Railway Postgres with pgvector available | `DATABASE_URL=postgresql://...` injected by Railway |
| Queue/cache | Railway Redis | `REDIS_URL=redis://...` |
| Worker | Railway worker service from same image | `bash scripts/start_worker.sh worker` |
| Scheduler | Railway worker/cron-style service from same image | `bash scripts/start_worker.sh beat` |
| Secrets | Railway variables | Slack, Anthropic, HubSpot, connector, encryption config |
| Encryption | Local fallback key for beta | `KMS_PROVIDER=none`, `TOKEN_ENCRYPTION_KEY=...` |

`railway.toml` points Railway at the `Dockerfile`, uses `/health` for health checks, and starts the web process with `scripts/start_web.sh`. The start script converts Railway's `postgresql://` URL into SQLAlchemy's required `postgresql+asyncpg://`, runs `alembic upgrade head`, then starts Uvicorn.

## Required Railway Variables

```bash
BETA_DEPLOY_TARGET=railway
APP_BASE_URL=https://your-railway-domain.up.railway.app
ENVIRONMENT=beta

DATABASE_URL= # Railway Postgres plugin injects this
REDIS_URL=    # Railway Redis plugin injects this

SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=

TOKEN_ENCRYPTION_KEY= # 64 hex chars
KMS_PROVIDER=none
KMS_KEY_ID=

ANTHROPIC_API_KEY=
CLASSIFIER_MODEL=claude-3-5-haiku-latest
DRAFT_MODEL=claude-3-5-sonnet-latest
SUMMARY_MODEL=claude-haiku-4-5-20251001

HUBSPOT_CLIENT_ID=
HUBSPOT_CLIENT_SECRET=
HUBSPOT_REDIRECT_URI=https://your-railway-domain.up.railway.app/hubspot/oauth_redirect

EMBEDDING_PROVIDER=voyage
VOYAGE_API_KEY=
OPENAI_API_KEY=

ERASURE_SECRET=
PRIVACY_CONTACT_EMAIL=
LEGAL_CONTACT_EMAIL=
SENTRY_DSN=
```

## Deployment Steps

1. Create a Railway project connected to this GitHub repo.
2. Add Railway Postgres and Redis services.
3. Add the variables above to the web service.
4. Deploy the web service from `main`.
5. Confirm migrations run during startup in Railway logs.
6. Add worker and beat services using the same repo/image and these start commands:
   ```bash
   bash scripts/start_worker.sh worker
   bash scripts/start_worker.sh beat
   ```
7. Generate the Slack manifest for the Railway domain:
   ```bash
   scripts/configure-manifest.sh https://your-railway-domain.up.railway.app
   ```
8. Upload `slack-app-manifest-generated.yaml` in Slack app settings, then copy Slack credentials back into Railway variables.
9. Run preflight from an operator shell with a local ignored `.env.beta` mirroring Railway variables:
   ```bash
   .venv/bin/python scripts/beta_preflight.py --env-file .env.beta
   .venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live
   ```
10. Open `APP_BASE_URL`, click `Add to Slack`, and run `docs/deployment/private-beta-acceptance.md`.

## Smoke Checks

```bash
curl $APP_BASE_URL/health
.venv/bin/python scripts/smoke_kms.py
.venv/bin/python scripts/beta_preflight.py --env-file .env.beta --live
```

Done means:
- `/health` returns `{"status":"ok","db":"ok","redis":"ok"}`.
- Local-mode KMS smoke prints `KMS smoke ok: provider=none key_id=local`.
- Beta preflight reports all required checks as `PASS`.
- `/relay help` works after Slack install.
- App Home and `/relay settings` show setup progress.

## Security Notes

Railway beta uses the configured `TOKEN_ENCRYPTION_KEY` as the encryption root. This is acceptable for friendly beta validation only. Before Marketplace submission or broader external rollout, move back to the AWS KMS production path or implement an equivalent managed KMS provider for the chosen host.
