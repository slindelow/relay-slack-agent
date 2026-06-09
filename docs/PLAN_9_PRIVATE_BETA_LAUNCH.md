# Plan 9: Private Beta Launch + External User Readiness

## Summary

RELAY's backend product loop is largely implemented and tested, but it is not yet an installable product for external customer-success teams. Plan 9 turns RELAY into a private-beta Slack app that a friendly workspace can install, configure, and use in real Slack Connect channels before Slack Marketplace submission.

Private beta comes before Marketplace submission. The current private-beta hosting path is Railway for speed of setup and validation. AWS remains the hardened production/Marketplace path because it best supports AWS KMS, managed infrastructure controls, and eventual security review.

## Ownership Model

- Codex owns launch-enabling implementation branches under `codex/plan-9-*`.
- Claude owns review, security pressure-testing, and focused implementation branches under `claude/plan-9-*`.
- Both agents must update `docs/HANDOFF.md` before ending work and keep `tasks/STATUS.md` aligned when a Plan 9 workstream changes state.

## Workstreams And Done Metrics

### 1. Global Project Alignment

Tasks:
- Keep this file as the active shared Plan 9 source of truth.
- Keep `tasks/STATUS.md`, `docs/HANDOFF.md`, and `docs/CLAUDE_OPERATING_BRIEF.md` pointed at Plan 9.
- Keep `README.md` honest about current state: backend mostly built, external launch readiness still underway.

Done means:
- A fresh agent reading only `docs/HANDOFF.md`, `tasks/STATUS.md`, and `docs/CLAUDE_OPERATING_BRIEF.md` knows Plan 9 is active.
- No shared coordination doc says Plan 1 is the current build plan.
- README describes private-beta readiness gaps clearly.

### 2. Deployment Foundation

Tasks:
- Document production topology for FastAPI web, Celery worker, Celery beat/SLA poller, Postgres with pgvector, Redis, migrations, health checks, Sentry, and secrets.
- Add minimal container/deploy artifacts without changing app behavior.
- Prefer Railway for the immediate friendly beta: web, worker, beat, Postgres with pgvector, Redis, Railway variables, Sentry, and local-mode encryption using `TOKEN_ENCRYPTION_KEY`.
- Keep AWS target architecture documented for production hardening: ECS/Fargate, RDS Postgres with pgvector, ElastiCache Redis, Secrets Manager, CloudWatch, Sentry, and AWS KMS.

Done means:
- A new deploy can run `alembic upgrade head`, start web, worker, and beat processes.
- `/health` returns `200` with `db: ok` and `redis: ok` in beta.
- `celery inspect ping` succeeds against the beta worker.
- One deployment runbook lists exact process commands and required env vars.

### 3. Slack App Distribution

Tasks:
- Maintain a checked-in Slack app manifest for `/relay`, OAuth, events, interactivity, App Home, bot scopes, and uninstall events.
- Provide a hosted private-beta install path from the deployed app.
- Document Slack configuration values tied to `APP_BASE_URL`.

Done means:
- A Slack admin can click one install link and complete OAuth.
- Install creates or updates a `Workspace`, stores encrypted bot token, and seeds default SLA policies.
- Slack event subscriptions and interactivity point to the deployed domain.
- A test workspace can run `/relay help` successfully after install.

### 4. Admin Onboarding UX

Tasks:
- Make App Home and `/relay settings` show setup state and next actions. Initial `/relay settings` setup summary is present.
- Provide admin paths for HubSpot, source connectors, channel registration, deletion, and connector purge.
- Add a first-admin/bootstrap rule so the installer can administer RELAY without manual DB edits. Current beta bootstrap promotes the first `/relay settings` user when the workspace has zero admins.

Done means:
- A fresh workspace can complete setup without direct database access.
- App Home shows Slack install, first admin, registered channel, CRM, and source-connector state accurately.
- `/relay settings` exists and returns useful setup controls or links.
- At least one happy-path onboarding test covers install -> admin setup -> channel registration.

### 5. Connector + CRM Readiness

Tasks:
- Finish HubSpot company/account upsert. Initial HubSpot company upsert to `CustomerAccount` is present.
- Make Google Drive/GitHub connector setup admin-driven instead of dependent on local fallback env vars. Initial beta setup modals are available through `/relay settings`.
- Encrypt connector credentials with the production key strategy. Connector setup stores encrypted credentials in `SourceConnector`.
- Show sync status, last sync time, failure reason, and retry path. `/relay settings` shows source status and can enqueue sync.

Done means:
- HubSpot sync creates or updates `CustomerAccount` rows from mocked or real HubSpot company payloads.
- Google Drive/GitHub connector records can be created, synced, disconnected, and purged from Slack UI.
- Source chunks are embedded and retrievable by `/relay ask`.
- Failed connector sync shows user-visible status and redacted logs.

### 6. Production Security + KMS

Tasks:
- Keep Railway beta on `KMS_PROVIDER=none` with a strong `TOKEN_ENCRYPTION_KEY`; validate with `scripts/smoke_kms.py`.
- Keep AWS KMS implementation and IAM documentation ready for the later hardened production path.
- Store workspace DEKs using AWS KMS before Marketplace/broader external rollout; keep legacy fallback only for migration.
- Review public/admin endpoints for auth, Slack verification, role checks, and redacted logs.

Done means:
- New workspace, CRM, and connector tokens use workspace DEK encryption.
- Railway beta encryption smoke passes with `KMS_PROVIDER=none`.
- AWS KMS mock/unit tests and one integration-style test pass before production hardening.
- Legacy fallback path is documented and is acceptable only for friendly Railway beta.
- Security tests pass and no secret/token appears in logs.

### 7. End-to-End Beta Validation

Tasks:
- Run a real Slack Connect flow: install, register external channel, classify a customer question, alert owner, claim, generate draft, approve, post, index memory.
- Validate connector purge, workspace deletion, uninstall cleanup, and individual user erasure.
- Validate classifier on a small labeled beta dataset.
- Use `docs/deployment/private-beta-acceptance.md` as the manual beta run script until Slack/Railway credentials are available in CI.

Done means:
- Full live flow succeeds in one test workspace without manual DB intervention.
- Approved response posts only after human approval.
- Classifier reaches precision >= 0.80 and recall >= 0.70 on the chosen validation set, or thresholds are adjusted and documented.
- Workspace deletion removes tenant data in CI-backed test and beta smoke test.

### 8. External User Packaging

Tasks:
- Rewrite user/operator docs for beta installation, setup, permissions, limitations, support, and deletion.
- Replace placeholder legal emails/domains in public pages.
- Create a private-beta user walkthrough with exact Slack steps.

Done means:
- A non-AI-literate CS admin can understand RELAY in under 2 minutes.
- Setup instructions avoid engineering jargon where possible.
- Legal pages use real contact details and production sub-processors.
- Private beta guide covers install, setup, daily use, troubleshooting, and deletion.

### 9. Marketplace Preparation After Beta

Tasks:
- Convert beta findings into Marketplace fixes.
- Finalize scope justification, reviewer sandbox, legal pages, uptime evidence, and security notes.
- Prepare Marketplace submission assets and checklist.

Done means:
- Reviewer sandbox can be seeded and walked through in under 15 minutes.
- Slack scope justification matches the manifest exactly.
- Marketplace submission checklist has no placeholders.
- At least one beta workspace has completed the core loop before submission.

## Required Test Baseline

- `.venv/bin/python -m pytest -q` stays green.
- Add focused tests as workstreams land: `/relay settings`, first-admin bootstrap, Slack manifest consistency, HubSpot upsert, KMS provider/local smoke, connector setup, deployment smoke checks, and live beta acceptance script.

## Explicit Assumptions

- Private beta comes before Slack Marketplace submission.
- Railway is the immediate private-beta hosting path; AWS remains the hardened production path.
- Slack handlers ack first; LLM and external calls stay in workers; Postgres RLS remains the tenant boundary; generated customer replies require human approval.
