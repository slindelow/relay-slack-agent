# PRD: Plan 7 — Marketplace Readiness

## Introduction

RELAY is functionally complete after Plan 6. This plan does not add new product features — it makes RELAY safe, reviewable, and publishable on the Slack App Marketplace. The work is: KMS envelope encryption, full deletion flows, privacy/legal pages, scope justification, and a reviewer sandbox. Without this plan, RELAY cannot be submitted to Slack.

**Dependency:** Plans 1–6 complete (full product flow working).

---

## Goals

- Upgrade token encryption from standalone AES-256-GCM to envelope encryption (cloud KMS for the master key).
- Implement all required deletion flows: workspace, connector, individual user (GDPR Art. 17).
- Publish: privacy policy, ToS, sub-processor disclosure page.
- Write scope justification narrative for Marketplace submission.
- Build a reviewer sandbox with demo data and an end-to-end test walkthrough.
- Set up production monitoring (Sentry, uptime checks, health dashboard).

---

## User Stories

### US-001: Envelope encryption — KMS-wrapped DEK per workspace
**Description:** As a security engineer, I need each workspace's tokens encrypted with a per-workspace data encryption key (DEK) wrapped by a cloud KMS master key, so that a DB dump without KMS access is useless.

**Acceptance Criteria:**
- [ ] `relay/crypto.py` extended with `generate_dek()`, `wrap_dek(dek, kms_client)`, `unwrap_dek(wrapped_dek, kms_client)` using AWS KMS (boto3) or GCP KMS (google-cloud-kms) behind a `KMSProvider` abstraction
- [ ] New column on `workspaces`: `wrapped_dek` (bytes), `kms_key_id` (str) — added via migration `0007_plan7_kms.py`
- [ ] `WorkspaceToken` encryption: encrypt with workspace DEK (AES-256-GCM), not the global `TOKEN_ENCRYPTION_KEY`
- [ ] `CrmConnection` encryption: same pattern
- [ ] `SourceConnector` credentials encryption: same pattern
- [ ] Migration script: for existing rows, re-encrypt from global key → DEK (run offline, not in-place in alembic)
- [ ] `relay/crypto.py` maintains backward compatibility: if `wrapped_dek` is null, fall back to global key (facilitates migration)
- [ ] `TOKEN_ENCRYPTION_KEY` env var is still accepted but marked deprecated in config
- [ ] Unit tests: encrypt/decrypt roundtrip with mocked KMS; verify fallback path works
- [ ] Typecheck passes

### US-002: Workspace deletion flow — `/relay delete-workspace-data`
**Description:** As a Marketplace reviewer, I need to verify that uninstalling RELAY completely removes all workspace data so I can approve the privacy compliance requirement.

**Acceptance Criteria:**
- [ ] `/relay delete-workspace-data` slash command handler in `relay/commands/delete.py`
- [ ] On invocation: shows a confirmation modal "This will permanently delete all RELAY data for your workspace. This cannot be undone."
- [ ] On confirmation: enqueues `delete_workspace_data(workspace_id)` Celery task
- [ ] `delete_workspace_data` task: deletes in cascade order — `knowledge_chunks` → `knowledge_entries` → `source_documents` → `source_connectors` → `drafts` → `retrieval_logs` → `impact_metrics` → `feedback_signals` → `alerts` → `snoozes` → `assignments` → `question_events` → `questions` → `messages` → `monitored_channels` → `customer_accounts` → `users` → `workspace_tokens` → `workspace_settings` → `sla_policies` → `crm_connections` → `workspaces`
- [ ] Writes a final `audit_log` entry before the workspace row is deleted: `event_type="workspace_deleted"`, actor, timestamp
- [ ] `workspace_deletion_jobs` table tracking: `workspace_id`, `status` (pending/complete/failed), `started_at`, `completed_at`
- [ ] On `app_uninstalled` Slack event: immediately sets `workspace_tokens.is_revoked = true` and enqueues deletion job
- [ ] Functional test: create workspace + full data tree, run deletion, verify all rows gone
- [ ] Typecheck passes

### US-003: Connector-level purge
**Description:** As an admin, I want to disconnect a source connector and purge all derived knowledge so RELAY retains no data from that source.

**Acceptance Criteria:**
- [ ] `/relay settings` shows a "Disconnect + Purge" button per connected source
- [ ] On confirm: calls `Connector.purge(workspace_id)` → deletes all `knowledge_chunks` and `source_documents` for that connector
- [ ] Updates `source_connectors.disconnected_at`
- [ ] Confirmation ephemeral: "Google Drive disconnected. All indexed content removed."
- [ ] Typecheck passes

### US-004: Individual user erasure (GDPR Art. 17)
**Description:** As a data protection officer, I need to erase all data associated with a specific user on request, without deleting the entire workspace.

**Acceptance Criteria:**
- [ ] `DELETE /relay/admin/users/{slack_user_id}/erase` FastAPI endpoint
- [ ] Requires `relay_role = "admin"` and a signed confirmation token in the request body
- [ ] Nullifies PII fields on `users` row: `display_name = null`, `email = null`, sets `deleted_at`
- [ ] Nullifies `actor_slack_user_id`, `actor_user_id` on `audit_log` rows for this user (retain event_type for compliance)
- [ ] Nullifies `actor_user_id` on `question_events` for this user
- [ ] Logs: `audit_log` entry `event_type="user_erased"` (with admin actor, user entity_id)
- [ ] Does NOT delete `questions`, `assignments`, `alerts` — only PII fields
- [ ] Returns 200 with confirmation JSON `{erased: true, user_id}`
- [ ] Typecheck passes

### US-005: Privacy policy, ToS, and sub-processor disclosure page
**Description:** As a Marketplace reviewer, I need public legal pages describing what data RELAY collects, how long it is retained, what sub-processors are used, and how users request deletion.

**Acceptance Criteria:**
- [ ] `/privacy` hosted page (static HTML or FastAPI route) containing:
  - Data collected (message excerpts, question metadata, account data, drafts)
  - Retention policy (matches the table in RELAY_PRD.md: 90d raw excerpts, 1y metadata, etc.)
  - Sub-processors listed: Anthropic (LLM, ZDR setting enabled, no training), embedding provider, hosting provider, Sentry
  - User rights: how to request deletion (link to `/relay delete-workspace-data` docs)
  - Contact email for DPAs
- [ ] `/terms` hosted page with standard SaaS ToS
- [ ] `/sub-processors` hosted page listing all third-party processors with: name, service, data sent, region, DPA link
- [ ] All three pages accessible without authentication
- [ ] Typecheck passes (FastAPI route returns 200)

### US-006: Scope justification narrative
**Description:** As a Marketplace reviewer, I need written justification for every Slack OAuth scope RELAY requests, explaining exactly why it is necessary and what data it accesses.

**Acceptance Criteria:**
- [ ] `docs/marketplace/scope-justification.md` created with one paragraph per scope:
  - `groups:history` — read messages in Slack Connect channels to detect customer questions
  - `groups:read` — enumerate private channels the bot is in (registered channels)
  - `channels:read` — check if bot is in a channel during registration
  - `chat:write` — post approved responses and alert DMs
  - `im:write` — send DM alert cards to CSMs
  - `users:read` — resolve CSM display names for alert cards
  - `commands` — register `/relay *` slash commands
- [ ] Document confirms: no `channels:history` (internal channels not monitored), all connector scopes marked optional
- [ ] Typecheck does not apply; reviewer will read this directly

### US-007: Reviewer sandbox with demo data
**Description:** As a Slack Marketplace reviewer, I need a sandbox workspace pre-loaded with demo data where I can walk through the full RELAY flow end-to-end.

**Acceptance Criteria:**
- [ ] `scripts/seed_reviewer_sandbox.py` creates: 1 workspace, 2 customer accounts (Enterprise + Starter), 2 registered Slack Connect channels, 3 open questions (one past SLA, one snoozed, one claimed), 1 pending draft, 2 resolved questions with knowledge_entries
- [ ] Seed script is idempotent: re-running it resets the sandbox to a clean state
- [ ] `docs/marketplace/reviewer-walkthrough.md` documents step-by-step: install app → register channel → receive alert → claim → draft → approve → verify sent → delete workspace data
- [ ] All steps in walkthrough produce the expected Slack UI outputs
- [ ] Typecheck passes for seed script

### US-008: Production monitoring
**Description:** As an operator, I need error tracking and uptime monitoring so I know when RELAY is failing in production.

**Acceptance Criteria:**
- [ ] Sentry SDK integrated: `relay/api/main.py` initializes Sentry with DSN from `SENTRY_DSN` env var
- [ ] Sentry captures unhandled exceptions in FastAPI request handlers, Bolt action handlers, and Celery tasks
- [ ] `SENTRY_DSN` is optional: if unset, Sentry is skipped silently (no crash at startup)
- [ ] `/health` endpoint (already exists) extended to include: `db: ok|error`, `redis: ok|error`; returns 503 if either dependency is down
- [ ] Celery worker health: `celery inspect ping` returns success in CI environment
- [ ] Typecheck passes

---

## Functional Requirements

- FR-1: Envelope encryption: a plaintext DB dump without KMS access must not expose any decryptable tokens.
- FR-2: `/relay delete-workspace-data` must completely remove all workspace data — zero rows remain in any tenant table after completion.
- FR-3: Privacy policy correctly lists all sub-processors including Anthropic with ZDR/no-training setting confirmed.
- FR-4: Reviewer sandbox seed is idempotent.
- FR-5: `/health` returns 503 when DB or Redis is unreachable.
- FR-6: Sentry initialization does not crash the server if `SENTRY_DSN` is not set.

---

## Non-Goals (Out of Scope)

- SOC 2 Type II audit (begin after first paid pilots, post-launch).
- HIPAA compliance — not a healthcare product.
- Per-workspace custom KMS keys — single KMS key region per deployment in v1.
- EU data residency — single region deployment in v1; document that in privacy policy.
- Automated Marketplace submission — this is a manual process.

---

## Technical Considerations

- KMS provider: AWS KMS using `boto3` with IAM role auth. GCP KMS is the alternative if hosting on GCP. Abstract behind `KMSProvider` so the choice is injectable.
- DEK rotation: out of scope for v1, but document the migration path in code comments.
- Deletion cascade: use explicit DELETE queries in dependency order rather than relying on Postgres CASCADE, so deletion can be logged and traced step by step.
- Sentry: use `sentry-sdk[fastapi,celery]` extras for automatic instrumentation.
- `/health` DB check: run `SELECT 1` in a timeout context; Redis check: `ping` with 1s timeout.

---

## Success Metrics

- Marketplace submission accepted without security/privacy rejections.
- `/relay delete-workspace-data` deletes all rows verified by functional test.
- Envelope encryption: penetration test (or internal review) confirms DB dump is not decryptable without KMS.
- Reviewer sandbox demo completes end-to-end in under 15 minutes.

---

## Open Questions

- AWS KMS or GCP KMS — depends on chosen hosting provider.
- Should the privacy policy be a static HTML page (simpler, reviewer-friendly) or a FastAPI template route?
- Pilot program timeline: how many pilot workspaces before Marketplace submission?
