# RELAY — Full Revised Product & Architecture Plan

> **Version:** 2.0 — Revised after 6-agent stress-test review  
> **Status:** Source of truth for all implementation work

## Summary

Build **RELAY**, a public Slack Marketplace app for CSM and support teams managing customer Slack Connect channels. RELAY detects unanswered customer questions, retrieves account and technical context from CRM/docs/GitHub, drafts cited responses for human approval, tracks the full question lifecycle with deterministic SLA enforcement, and builds institutional memory from resolved answers.

This is a **production beta/Marketplace-ready** target, not a demo MVP. Architecture is async-first, privacy-first, multi-tenant, and validation-led.

Core principle:

> RELAY is a deterministic workflow system with bounded agentic reasoning. The agent interprets and drafts. The workflow owns state, permissions, timers, and side effects.

---

## Product Strategy

### Beachhead ICP

**B2B SaaS companies with 10–100 active Slack Connect customer channels**, a small-to-mid CS team, and no dedicated Slack-native customer-response tooling.

- **User:** CSM or support lead monitoring customer Slack Connect channels.
- **Buyer:** VP or Head of Customer Success — cares about SLA coverage, renewal risk, audit trails, and team efficiency.
- **Economic trigger:** A missed SLA that contributed to a churn event or executive escalation.

### Core Product Promise

RELAY answers four questions for CS teams:

1. Which customer asks are going unanswered right now?
2. How urgent is this account given its CRM context?
3. What internal truth should we use to respond?
4. Are we improving response quality and SLA performance over time?

### Differentiation

RELAY is not generic Slack AI. It adds durable account-state workflow:

- Tracks customer asks as first-class objects with SLA timers.
- Uses CRM account context (tier, ARR, renewal date, health score) to prioritize risk.
- Retrieves evidence from approved docs/GitHub/prior resolutions.
- Requires citations before producing a customer-facing draft.
- Keeps human approval mandatory — RELAY never posts to customers autonomously.
- Measures SLA compliance and draft quality over time.
- Builds reusable resolution memory from approved answers.

**Competitor positioning:** Front and Zendesk require pulling customers out of Slack. Native Slack AI has no account-state tracking, no CRM context, no SLA enforcement. RELAY treats Slack Connect like a support queue without disrupting the Slack-native relationship.

### Non-Goals for Launch

- No autonomous customer-channel posting.
- No Gmail (high-sensitivity scope, adds Marketplace review burden).
- No Salesforce at launch — HubSpot first; Salesforce designed-in from day one.
- No Jira/Linear/Confluence at launch.
- No customer-hosted deployment in v1.
- No per-user (CSM) OAuth token for posting — bot posts with attribution.
- No broad workspace-wide channel scraping.

---

## Validation Gate Before Product Build

**Do not write product code until the classifier passes the quality gate.**

### Phase 0 Deliverables

1. Create a labeled dataset of 500+ realistic synthetic/anonymized Slack Connect-style messages including: greetings, FYIs, ambiguous status updates, bug reports, questions, sales/procurement asks, threaded side-conversations, urgent incidents.
2. Build an offline classifier evaluation harness.
3. Test at least two prompt variants.
4. Run threshold sweep from 0.50 to 0.95.

### Label Schema

| Field | Type | Notes |
|---|---|---|
| `is_customer_message` | bool | From the customer (external) side? |
| `requires_response` | bool | Needs a response from the internal team? |
| `intent` | enum | question / bug_report / access_request / status_update / greeting / blocker / other |
| `urgency` | enum | critical / high / normal / low |
| `should_start_sla` | bool | Should this trigger SLA tracking? |
| `expected_owner_action` | string | What should the CSM do? |
| `notes` | string | Edge case explanation if ambiguous |

### Quality Gates

- Precision ≥ 80% on `requires_response` at chosen open threshold.
- Recall ≥ 70% on `requires_response` at chosen open threshold.
- False-positive rate acceptable in pilot review.
- P95 time from Slack event receipt to open-question creation ≤ 5 minutes.

### Feedback Loop (Ongoing)

Every in-product correction becomes a labeled example. Log all of: mark not a question, mark as question, change urgency, draft accepted/discarded/regenerated, manual resolution, incorrect source flagged, incorrect response detection. Store in `feedback_signals` table. Run weekly review. Export labels. Recalibrate thresholds on schedule.

---

## WAT Boundary

### Deterministic Workflow Layer

Owns: Slack event acking, workspace install and token storage, channel registration, account-to-channel mapping, CRM sync, customer/internal sender detection, SLA policy assignment and timer scheduling, alert deduplication and delivery, snooze/claim/escalation, backup owner escalation, human approval gate before posting, audit logging, retention and deletion.

### Agentic Reasoning Layer

Returns structured outputs only: intent classification, urgency assessment, response-quality confidence, context planning, source synthesis and reranking, draft generation, account risk interpretation from CRM context, ambiguous response detection.

### Rule

> The agent recommends. The workflow commits.

---

## Technical Architecture

### Services

- **Slack App/API Server:** Python Slack Bolt (async) + FastAPI.
- **Async Queue:** Redis-backed Celery.
- **Workers:** classification, SLA polling (every 60 seconds), source sync, embedding jobs, draft generation.
- **Database:** PostgreSQL 15+ with pgvector.
- **LLM Layer:** Anthropic Claude — Sonnet for drafting/synthesis, Haiku for classification. Both via provider abstraction. ZDR/no-training API settings required.
- **Embedding Layer:** Voyage or OpenAI embeddings behind `EmbeddingProvider` abstraction. Model and dims stored on each vector row.
- **Connector Layer:** HubSpot, docs, GitHub — each behind a normalized `Connector` interface (sync, search, citation, disconnect, purge).
- **Admin Surface:** Slack App Home + lightweight hosted admin console.
- **Observability:** Sentry, structured logs, per-workspace metrics, health checks.

### Critical Architecture Decisions (Non-Negotiable)

**1. Bolt + FastAPI query Postgres directly.**
MCP is not the internal database access layer. MCP/tool interfaces expose constrained context tools to the reasoning layer during inference only.

**2. Ack Slack in < 3 seconds, always.**
Bolt handler flow: verify signature → persist minimal event envelope + idempotency key → return HTTP 200 → `process_slack_event.delay(payload)`. No LLM call, CRM call, GitHub call, docs search, or embedding call happens before ack.

**3. Idempotency key = `{team_id}:{channel_id}:{message_ts}`.**
Use `SETNX` on the dedup key in Redis before any processing. Skip if already processed.

**4. Customer/internal detection is deterministic, not heuristic.**
At channel registration: call `conversations.info`, extract the external Slack Connect workspace ID from `shared_channel_invite` context, store as `customer_slack_team_id` on `monitored_channels`. Classify any message where `sender.team_id` matches that value as a customer message. Zero per-message API calls. External Slack Connect user IDs may not resolve via `users:read` — display as `Customer (external)` + raw user ID.

**5. Post as bot with attribution for v1.**
"Posted by RELAY on behalf of @Sofia after her approval." Per-user OAuth is post-launch.

**6. Cron/60-second polling for SLA timers.**
Worker scans for `questions` where `state IN ('open', 'snoozed')` and `next_alert_at < now()`. Partial index on `(next_alert_at, workspace_id)` with that WHERE clause.

---

## Security, Privacy, and Compliance

### Token Encryption

Envelope encryption: AES-256-GCM for token payload. Per-workspace data encryption key (DEK). DEK wrapped by cloud KMS (AWS KMS, GCP KMS, or HashiCorp Vault). Rotate DEKs on schedule and on incident. Never log the key or encrypted values.

### Redis Security

TLS and auth required. Job payloads must be minimal — pass DB IDs, not full message content. Store large context in Postgres; pass IDs through queue. Short TTL on transient job results.

### Sub-Processors

Publish a sub-processor/data-use page naming at minimum: LLM provider (Anthropic), embedding provider, hosting provider, error monitoring (Sentry). Include: what data is sent, ZDR/no-training setting, data region, DPA links. Required before any EU enterprise customer can sign.

### Prompt Injection Defense

All external and customer-generated content is untrusted:
- Wrap retrieved content in explicit XML delimiters (`<retrieved_source trust="external">`).
- System prompt instructs model to treat content inside delimiters as untrusted data, not instructions.
- Validate all structured outputs against JSON Schema before acting on them.
- Redact or escape instruction-like patterns in retrieved content before inclusion.

### Data Retention

| Data type | Default TTL |
|---|---|
| Raw tracked Slack message excerpts | 90 days post-resolution |
| Open/resolved question metadata | 1 year |
| Drafts and source bundles | 180 days |
| Audit logs | 1 year (customer-configurable) |
| Embeddings / source chunks | Until connector disconnect or workspace deletion |
| Redis job results | Minutes to hours (shortest practical TTL) |

### Deletion Flows

- `/relay delete-workspace-data` — Slack slash command, testable by Marketplace reviewers.
- Admin console deletion page.
- Connector-level purge (removes derived knowledge chunks and embeddings).
- Individual user erasure flow (GDPR Art. 17).
- `workspace_deletion_jobs` table to track async deletion progress.
- On `app_uninstalled` event: immediately set `workspace_tokens.is_revoked = true`.

### Audit Log Schema

```
id, workspace_id, actor_user_id, actor_slack_user_id, actor_ip, user_agent,
event_type (enum), entity_type, entity_id, old_value (jsonb, redacted),
new_value (jsonb, redacted), created_at
```

Append-only at DB role level: `REVOKE UPDATE, DELETE ON audit_log FROM relay_app`.

### Marketplace Scope Strategy

- Request minimum Slack scopes. Justify every scope in one paragraph in submission form.
- `groups:history` for Slack Connect channels. Request `channels:history` only if internal public channels are needed.
- Mark all connector scopes optional.
- Prepare written security narrative: who reads what, where it goes, how long it stays, how it is deleted.

---

## Multi-Tenancy

- Every tenant table includes `workspace_id`.
- `Workspace.id` = internal UUID (PK). `Workspace.slack_team_id` = Slack's string team ID (UNIQUE). Reinstall reuses existing `workspace` row, clears `uninstalled_at`, rotates bot token.
- Enable PostgreSQL Row Level Security (RLS) on all tenant tables. Set `app.current_workspace_id` in every session before queries.

### Tables Requiring RLS

`workspace_tokens`, `workspace_settings`, `sla_policies`, `users`, `customer_accounts`, `monitored_channels`, `messages`, `questions`, `question_events`, `alerts`, `assignments`, `snoozes`, `drafts`, `source_connectors`, `source_documents`, `knowledge_chunks`, `knowledge_entries`, `retrieval_logs`, `feedback_signals`, `impact_metrics`, `audit_log`, `workspace_feature_flags`

### pgvector Tenant Safety

Every vector row includes `workspace_id`. Retrieval prefilters by `workspace_id` before vector similarity search. Store `embedding_model`, `embedding_dims`, and `content_hash` on each chunk. Evaluate per-workspace partitioning if index performance degrades.

---

## Database Schema (Core Tables)

**`workspaces`** — id (UUID PK), slack_team_id (UNIQUE), slack_team_name, installed_at, uninstalled_at, deleted_at

**`workspace_tokens`** — workspace_id (FK), token_type, encrypted_token (bytes), encrypted_token_nonce (bytes/12), scopes, is_revoked, revoked_at

**`workspace_settings`** — workspace_id (UNIQUE FK), question_confidence_threshold_open (default 0.85), question_confidence_threshold_candidate (default 0.60), classifier_variant, alert_digest_mode, quiet_hours_start, quiet_hours_end

**`workspace_feature_flags`** — workspace_id (FK), flag_name, is_enabled, value (jsonb)

**`sla_policies`** — workspace_id (FK), tier_name, response_window_minutes, escalation_window_minutes

**`users`** — workspace_id (FK), slack_user_id, display_name, email, relay_role, is_ooo

**`crm_connections`** — workspace_id (FK), crm_provider ('hubspot' | 'salesforce'), encrypted_access_token, encrypted_refresh_token, connected_at, last_synced_at, sync_status

**`customer_accounts`** — workspace_id (FK), name, domain, crm_provider, external_crm_id, owner_user_id (FK), backup_owner_user_id (FK), tier, sla_policy_id (FK), lifecycle_stage, arr, renewal_date, health_score, external_crm_url, manual_tier_override, deleted_at

**`monitored_channels`** — workspace_id (FK), account_id (FK), slack_channel_id, customer_slack_team_id, is_ext_shared, is_active, registered_at, registered_by_user_id

**`messages`** — workspace_id (FK), channel_id (FK), slack_message_ts, is_customer_message, raw_excerpt, classification_label, classification_confidence, classification_variant

**`questions`** — workspace_id (FK), channel_id (FK), message_id (FK), account_id (FK), state (enum: detected/open/claimed/resolved/expired), next_alert_at, last_alert_at, alert_count, snoozed_until, urgency, title_excerpt, created_at, resolved_at

**`question_events`** — question_id (FK), workspace_id, event_type, actor_user_id, metadata (jsonb), created_at

**`alerts`** — question_id (FK), workspace_id, recipient_user_id (FK), channel, sent_at, acknowledged_at, alert_type

**`assignments`** — question_id (FK), workspace_id, assignee_user_id (FK), assigned_by_user_id, assigned_at, unassigned_at

**`snoozes`** — question_id (FK), workspace_id, snoozed_by_user_id (FK), snoozed_until, reason, created_at

**`drafts`** — question_id (FK), workspace_id, evidence_bundle (jsonb), customer_draft (text), internal_brief (text), confidence, status (pending/approved/discarded/sent), editor_user_id, approved_by_user_id, sent_at

**`source_connectors`** — workspace_id (FK), connector_type (enum), config (jsonb), encrypted_credentials, sync_status, last_synced_at, disconnected_at

**`source_documents`** — workspace_id (FK), connector_id (FK), external_id, title, url, content_hash, provider_updated_at, last_synced_at

**`knowledge_chunks`** — workspace_id (FK), source_document_id (FK nullable), knowledge_entry_id (FK nullable), chunk_index, content (text), embedding (vector), embedding_model, embedding_dims, content_hash, created_at

**`knowledge_entries`** — workspace_id (FK), question_id (FK nullable), title, summary, customer_question, internal_answer, source_bundle (jsonb), reuse_count, created_at

**`retrieval_logs`** — draft_id (FK), workspace_id, sources_used (jsonb), query, retrieved_at

**`feedback_signals`** — workspace_id (FK), message_id/question_id/draft_id (FK nullable), actor_user_id, correction_action (enum), original_label, corrected_label, original_confidence, notes, created_at

**`impact_metrics`** — workspace_id (FK), account_id (FK), question_id (FK), time_to_first_alert_seconds, time_to_first_draft_seconds, time_to_send_seconds, sla_met, draft_accepted, draft_edit_distance, alert_to_action, created_at

**`audit_log`** — workspace_id, actor_user_id, actor_slack_user_id, actor_ip, user_agent, event_type, entity_type, entity_id, old_value (jsonb), new_value (jsonb), created_at

---

## Integrations

### Slack

Required scopes: `channels:read`, `groups:read`, `groups:history`, `chat:write`, `im:write`, `users:read`, `commands`

Key constraints:
- Bot must be manually invited to each Slack Connect channel — no programmatic join.
- Reviewer sandbox with demo channels required for Marketplace approval.
- External Slack Connect user IDs may not resolve via `users:read` — display as "Customer (external)."

### HubSpot (Launch CRM)

OAuth scopes: `crm.objects.companies.read`, `crm.objects.contacts.read`, `crm.objects.deals.read`

Sync: Admin authorizes HubSpot → RELAY imports and normalizes companies → Admin maps to registered channels → Scheduled sync updates tier, owner, ARR, renewal date, lifecycle stage. CRM context injected into classification urgency and draft prompts. CRM provider abstraction: Salesforce is next without changing SLA/alerting/drafting logic.

### Docs (One Provider at Launch)

Notion or Google Drive/Docs. Admin selects allowed pages/folders. RELAY syncs, chunks with title/URL/updated timestamp. Re-syncs periodically. Source staleness shown in draft modal.

### GitHub

Selected repositories only. Search issues, PRs, releases, changelogs, selected markdown docs. Cite issue/PR/release links with status, labels, assignee, updated time.

---

## Slack Surface Design

### Slash Commands

- `/relay register #channel account-name tier @owner`
- `/relay open`
- `/relay ask [question]`
- `/relay pulse`
- `/relay settings`
- `/relay delete-workspace-data`
- `/relay help`

### App Home

- Setup checklist (CRM, docs, GitHub, first channel)
- Connected source status and last sync time
- Registered channels and accounts
- Open unanswered questions
- **Review ignored/candidate messages** (escape hatch from silent ignore bucket)
- Accuracy/feedback summary (classification accuracy this week: X%)
- Impact metrics (SLA met rate, draft acceptance rate, alert-to-action rate)
- Alert preferences (digest mode, quiet hours, thresholds)

### Alert DM Card

Account name/tier/renewal proximity, question excerpt, time waiting/SLA deadline, urgency signal, primary/backup owner, conversation link, source sync status.

Actions: `View`, `Draft response`, `Snooze 30m`, `Mark not a question`, `Assign`, `Claim`

### Draft Modal

Customer question, account CRM context, internal evidence brief, proposed customer response, source citations (title/provider/link/excerpt/freshness/staleness warning), confidence level, risks/unknowns, editable response body.

Actions: `Send (bot-posted with attribution)`, `Save draft`, `Regenerate`, `Discard`

All Discard and Regenerate actions are logged as feedback signals.

### Auto-Acknowledgment Toggle

Optional per-channel bot message sent when a question is detected: "Our team has received your message and is on it." Configurable per channel. Default off.

### Per-Account Context Card

CSM-editable per account: key contacts and seniority, terminology aliases, classification overrides ("messages containing 'deploy' in this channel = question"), priority boost flag. Injected into classification and drafting prompts.

---

## SLA & State Machine

### 5 Visible Question States

```
detected → open → claimed → resolved
                          ↘ expired
```

Internal events tracked in `question_events`, not as user-visible states.

### Classification Thresholds (Empirically Validated in Phase 0)

- **≥ open_threshold (default 0.85):** Create question, start SLA.
- **≥ candidate_threshold (default 0.60):** Candidate — surface in "Review ignored/candidate messages."
- **< candidate_threshold with urgency markers** ("down," "outage," "blocking," "critical," "production"): Create lightweight review nudge. Do not silently ignore.
- **< candidate_threshold, no urgency markers:** Ignore. Logged for accuracy review.

Thresholds stored in `workspace_settings`, admin-configurable per workspace.

### Timer

Cron worker every 60 seconds: query for `questions` where `state IN ('open', 'snoozed')` and `next_alert_at < now()`. Partial index on `(next_alert_at, workspace_id)` with that WHERE clause. Create `alerts` record, send DM, update `last_alert_at`, `alert_count`, `next_alert_at`. Idempotency: check `alerts` table for recent alert on same question before sending.

### Coverage & Escalation

- Primary and backup owner per channel.
- If primary does not act within `escalation_window_minutes`: alert backup owner.
- `users.is_ooo` routes directly to backup.
- Bulk reassign available in App Home.
- Global snooze (pause all alerts for current user for N hours).

### Notification Fatigue Controls

Digest mode, quiet hours, minimum confidence threshold to alert, alert frequency cap, alert-to-action rate tracked in `impact_metrics`.

---

## Response Detection

Safe v1 rule: A message from an internal user (team_id matches `workspace.slack_team_id`) posted after the customer question changes the question to `possibly_answered`. A lightweight response classifier decides if it is a customer-facing answer or internal coordination. Low confidence → keep open, suppress duplicate noise. CSMs can always manually mark resolved, reopen, assign, add note.

---

## Retrieval & Drafting

### Context Assembly

1. Load question, account, SLA status, CRM context, recent thread/channel context.
2. Classify needed context types.
3. Query approved sources only (workspace source allowlist).
4. Rerank by: authority, freshness, account relevance, semantic similarity.
5. Build evidence bundle.
6. Generate internal brief.
7. If evidence meets threshold: generate cited customer draft.
8. If evidence is weak: return internal brief only. Block customer draft.

### Source Priority

1. Account-specific CRM context (renewal proximity, health score, lifecycle)
2. Current GitHub issue/PR/release status
3. Official docs or runbooks
4. Prior resolved customer answer (knowledge_entries)
5. Pre-ingested indexed channel history (knowledge_chunks) — not live Slack search

Note: Slack bot tokens cannot do cross-channel search. "Similar Slack discussion" is from pre-ingested indexed messages only.

### Strict Citation Policy

Every customer-facing draft must include per source: title, provider, link/permalink, short supporting excerpt, freshness timestamp, staleness warning if synced > N hours ago. No sufficient source → "I found no verified source. Here is an internal triage brief instead." RELAY does not fabricate a confident customer response.

### Draft Output Contract

```json
{
  "summary": "...",
  "evidence": [...],
  "confidence": 0.0-1.0,
  "customer_draft": "...",
  "internal_brief": "...",
  "risks_or_unknowns": "...",
  "recommended_next_action": "...",
  "requires_human_review": true
}
```

`requires_human_review` is always `true`.

---

## Implementation Phases

### Phase 0: Classifier Validation Sprint (Pre-Code Gate)

500+ labeled synthetic/anonymized messages with 7-field schema. Offline evaluation harness with two prompt variants. Threshold sweep. Validate empirically. **Gate: P ≥ 80%, R ≥ 70% before proceeding.**

### Phase 1: Foundation

Slack OAuth (reinstall-safe workspace upsert). Request signature verification. Async event queue (Celery/Redis — ack < 3s). Postgres schema with RLS on all tenant tables. Envelope token encryption (AES-256-GCM). App Home skeleton. Audit log base. `/relay help`, `/relay delete-workspace-data`. Workspace deletion cascade.

### Phase 2: CRM + Account Registry

HubSpot OAuth and account import. Normalize account fields to `customer_accounts`. Owner/tier/SLA mapping. Manual override. CRM provider abstraction (Salesforce-ready). Channel registration. `customer_workspace_id` stored at registration from `conversations.info`. Admin views.

### Phase 3: Message Intake + Classification

Slack Events API handler (ack < 3s, enqueue). Registered-channel filtering. Customer/internal sender classification using `customer_workspace_id`. Idempotent event storage. Async classification worker. Create `detected`/`open` questions. Candidate queue. Low-confidence urgent path. "Review ignored/candidate messages" in App Home. Feedback signals logged.

### Phase 4: SLA Engine + Alerts

60-second cron polling. `next_alert_at` logic with partial index. Alert records and deduplication. DM alert cards. Snooze/claim/assign/mark-not-a-question. Backup owner escalation. OOO flag and routing. Quiet hours and digest mode. Auto-acknowledgment toggle. Bulk reassign. Alert-to-action rate logged.

### Phase 5: Source Connectors + Embedding Pipeline

Connector interface (sync, search, citation, disconnect, purge). Docs connector (Notion or Google Drive/Docs). GitHub connector. Chunking with overlap. Embedding generation with `embedding_model`, `embedding_dims`, `content_hash` stored. Tenant-safe vector search. Source allowlists. Retrieval logs. Freshness timestamps and staleness warnings.

### Phase 6: Drafting + Approval

Evidence bundle construction with reranking. Prompt-injection-safe drafting (XML delimiters, untrusted content tagging). Strict citation enforcement. Draft modal with editable response, per-citation freshness, confidence, risks. Per-account context card injected into prompts. Discard/regenerate logged as feedback signals. Bot-posted approved response with CSM attribution. Resolution indexing.

### Phase 7: Feedback + Accuracy Loop

Feedback signals store. Weekly accuracy/false-positive review in Admin Console. Label export. Per-workspace classification accuracy stat in App Home. Threshold recalibration workflow.

### Phase 8: Account Pulse + Impact Metrics

Weekly account pulse (Block Kit/Canvas). SLA health, silent account detection, repeated issue themes. Impact metrics tab (time-to-draft, time-to-send, draft acceptance rate, edit distance, alert-to-action rate). `/relay pulse`, `/relay ask`.

### Phase 9: Marketplace Readiness + Pilot

5-10 CS team pilot program (30-day paid pilots, case studies). Public landing page, privacy policy, ToS/support. Sub-processor disclosure (Anthropic, embedding provider, hosting, Sentry). Scope justification narrative. Reviewer sandbox with demo data and full test walkthrough. Interactive deletion flow for reviewers. Monitoring and uptime checks.

---

## Acceptance Criteria

- Classifier meets quality gate on labeled holdout data (P ≥ 80%, R ≥ 70%).
- Slack events acked within 3 seconds.
- App installable via OAuth.
- HubSpot account sync works for selected pilot workspaces.
- Admins can register customer channels with `customer_workspace_id` stored.
- RELAY detects and tracks customer questions.
- SLA alerts fire within 5 minutes P95.
- Backup escalation fires when primary does not act.
- CSMs can claim, snooze, assign, resolve, correct, and bulk-reassign.
- Drafts require citations or are blocked and replaced by internal brief.
- Per-account context card fields injected into prompts.
- Auto-acknowledgment toggle works per channel.
- Low-confidence urgent messages create review nudges, not silence.
- "Review ignored messages" view is populated and actionable.
- Approved responses post as bot with attribution.
- Feedback signals logged for every correction action.
- Impact metrics visible to admins.
- Workspace and connector deletion flows work end-to-end.
- Privacy, sub-processor disclosure, scope-justification, landing pages exist for Marketplace review.
- Reviewer sandbox functional with full test walkthrough.
- Pilot program produced at least 3 documented case studies.

---

## Architectural Defaults (Non-Negotiable)

- MCP is inference-only. Bolt + FastAPI query Postgres directly.
- Ack Slack in < 3 seconds. All LLM/CRM/retrieval work is async.
- Cron polling (60s) with `next_alert_at` is the v1 SLA timer.
- 5 visible question states. Internal events in `question_events`.
- Bot-posted approved responses. Per-user OAuth is post-launch.
- Envelope encryption with per-workspace DEK path.
- RLS enforced at Postgres layer, not application layer only.
- `customer_workspace_id` stored at channel registration. Zero per-message API calls for sender classification.
- All customer-facing drafts require strict citations and human approval.
- Slack search is not a live retrieval source. It is a background ingestion pipeline.

---

## Post-Launch Roadmap

- **Salesforce CRM** — provider abstraction is ready; implementation next.
- **Jira/Linear** — engineering issue status in context assembly.
- **Confluence** — additional docs provider.
- **Sheets/CSV import** — fallback account import path.
- **Per-user OAuth (post as CSM)** — post-launch enhancement.
- **SOC 2 Type II audit** — begin in parallel with Phase 6–7.
- **KMS in production** — envelope encryption pattern is ready; cloud KMS provider is deployment-dependent.
