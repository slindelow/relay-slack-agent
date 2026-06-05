# PRD: Plan 6 — Feedback, Resolution Memory + Account Pulse

## Introduction

RELAY improves over time by turning approved responses into reusable knowledge and by surfacing patterns back to CS teams. This plan adds: resolution memory (storing approved answers as `knowledge_entries`), a structured feedback signal review flow, account pulse (weekly Block Kit digest per account), impact metrics visibility, and the `/relay ask` and `/relay pulse` slash commands.

**Dependency:** Plan 5 complete (drafts sent, feedback_signals written, impact_metrics rows exist).

---

## Goals

- Turn every sent response into a `knowledge_entry` so future drafts can cite prior answers.
- Give admins a weekly accuracy and false-positive review in App Home.
- Ship `/relay pulse` (account health digest) and `/relay ask` (manual retrieval).
- Make impact metrics (SLA met rate, draft acceptance rate, time-to-send) visible to admins.

---

## User Stories

### US-001: Add knowledge_entries and impact_metrics tables migration
**Description:** As a developer, I need the knowledge_entries table for resolution memory and the impact_metrics table for analytics.

**Acceptance Criteria:**
- [ ] Alembic migration `0006_plan6_memory.py`
- [ ] `knowledge_entries` table: `id` (UUID PK), `workspace_id` (FK), `question_id` (FK nullable), `title` (text), `summary` (text), `customer_question` (text), `internal_answer` (text), `source_bundle` (jsonb), `reuse_count` (int, default 0), `created_at`
- [ ] `impact_metrics` table (if not added in Plan 5): `id` (UUID PK), `workspace_id`, `account_id` (FK), `question_id` (FK), `time_to_first_alert_seconds` (int nullable), `time_to_first_draft_seconds` (int nullable), `time_to_send_seconds` (int nullable), `sla_met` (bool nullable), `draft_accepted` (bool nullable), `draft_edit_distance` (int nullable), `alert_to_action` (int nullable), `created_at`
- [ ] RLS policies on both tables
- [ ] ORM models `KnowledgeEntry`, `ImpactMetrics` added to `relay/db/models.py`
- [ ] Migration runs cleanly
- [ ] Typecheck passes

### US-002: Index approved responses as knowledge_entries
**Description:** As a developer, I want every sent response to automatically create a knowledge_entry so future drafts can cite prior answers for the same account or topic.

**Acceptance Criteria:**
- [ ] `relay/drafting/memory.py` implements `index_approved_response(workspace_id, question_id, draft_id)` async function
- [ ] Reads the question (title_excerpt, account_id), account name, and draft (customer_draft, internal_brief, evidence_bundle)
- [ ] Creates `KnowledgeEntry` row: `customer_question` = question title_excerpt, `internal_answer` = customer_draft, `source_bundle` = draft evidence_bundle, `summary` = LLM-generated one-sentence summary (Haiku)
- [ ] Embeds the `customer_question + internal_answer` text and stores in `knowledge_chunks` with `knowledge_entry_id` set (not `source_document_id`)
- [ ] Called from the `relay_send_draft` handler after the response is posted
- [ ] Unit tests: verify knowledge_entry created, chunk embedded, correct FK wiring
- [ ] Typecheck passes

### US-003: Retrieval uses knowledge_entries as a source
**Description:** As a developer, I want `retrieve()` to also search prior knowledge_entries so approved answers surface as evidence in future drafts.

**Acceptance Criteria:**
- [ ] `relay/connectors/retrieval.py` updated: include `knowledge_chunks` rows where `knowledge_entry_id IS NOT NULL` in the cosine search
- [ ] Retrieved knowledge_entry chunks show provider as `"relay_memory"` in citation output
- [ ] `KnowledgeEntry.reuse_count` incremented each time a chunk is included in an evidence bundle
- [ ] Unit test: a knowledge_entry chunk ranks above a stale docs chunk of equal semantic distance
- [ ] Typecheck passes

### US-004: `/relay ask` slash command
**Description:** As a CSM, I want to type `/relay ask <question text>` to get an immediate evidence retrieval without being in a question workflow — useful for ad-hoc lookups during a customer call.

**Acceptance Criteria:**
- [ ] `/relay ask <text>` handler in `relay/commands/ask.py`
- [ ] Calls `retrieve(workspace_id, query=text, top_k=5)` and `assemble_evidence(workspace_id, question_id=None)` (no question required)
- [ ] Responds in-thread with an ephemeral message listing top sources: title, provider, excerpt, link, freshness
- [ ] If zero results: ephemeral "No relevant sources found in connected knowledge base."
- [ ] Slash command registered in `relay/commands/register.py`
- [ ] Typecheck passes

### US-005: App Home — impact metrics tab
**Description:** As an admin, I want to see RELAY's performance data (SLA met rate, draft acceptance rate, time-to-send) in the App Home so I can evaluate its value.

**Acceptance Criteria:**
- [ ] App Home (relay/slack/home.py) gains an "Impact" section with rolling 30-day stats:
  - SLA met rate: `COUNT(sla_met=True) / COUNT(*)` where `sla_met IS NOT NULL`
  - Draft accepted rate: `COUNT(draft_accepted=True) / COUNT(*)` where `draft_accepted IS NOT NULL`
  - Median time to send (seconds → human-readable)
  - Total questions handled
- [ ] Stats computed from `impact_metrics` filtered by `workspace_id` and `created_at >= now() - 30 days`
- [ ] If no data yet: shows "No data yet — stats appear after your first sent response."
- [ ] Typecheck passes

### US-006: App Home — accuracy and feedback review
**Description:** As an admin, I want to see a weekly accuracy summary in the App Home that shows false-positive rate and lets me export labeled examples for classifier retraining.

**Acceptance Criteria:**
- [ ] App Home gains an "Accuracy" section showing rolling 7-day stats:
  - `mark_not_question` corrections: count this week vs last week
  - Classification accuracy rate: `(total - corrections) / total * 100`%
  - Link to export labeled feedback (see US-007)
- [ ] Stats read from `feedback_signals` where `correction_action = 'mark_not_question'`
- [ ] Typecheck passes

### US-007: Feedback export endpoint
**Description:** As an admin, I want to download this week's feedback signals as a JSONL file so I can use them to retrain or recalibrate the classifier.

**Acceptance Criteria:**
- [ ] `GET /relay/admin/feedback-export` FastAPI endpoint
- [ ] Returns a `.jsonl` file with one JSON object per `feedback_signals` row: `{message_text, original_label, corrected_label, correction_action, created_at}`
- [ ] Scoped to the requesting workspace (identified from Slack OAuth token in Authorization header)
- [ ] Optional query param `?days=7` (default 7, max 90)
- [ ] Requires `relay_role = "admin"` on the requesting user; returns 403 otherwise
- [ ] Typecheck passes

### US-008: `/relay pulse` slash command — account health digest
**Description:** As a CSM or manager, I want to run `/relay pulse [account-name]` to get a block-kit summary of an account's recent question activity, SLA performance, and CRM signals.

**Acceptance Criteria:**
- [ ] `/relay pulse` handler in `relay/commands/pulse.py`
- [ ] With no argument: returns summary of ALL accounts with open questions (sorted by urgency)
- [ ] With `account-name`: returns detailed pulse for that account
- [ ] Per-account pulse shows: open question count, SLA met rate (30d), last question resolved (date), renewal date proximity, account tier and ARR, backup owner if primary is OOO
- [ ] Response is ephemeral, formatted as Block Kit sections
- [ ] If account not found: ephemeral "Account not found. Run `/relay register` to add it."
- [ ] Slash command registered in `relay/commands/register.py`
- [ ] Typecheck passes

---

## Functional Requirements

- FR-1: Every sent response creates a `knowledge_entry` row and at least one `knowledge_chunks` embedding — verified by test.
- FR-2: `knowledge_entry` chunks are included in future `retrieve()` calls for the same workspace.
- FR-3: `reuse_count` is incremented each time a chunk is used in an evidence bundle.
- FR-4: Feedback export is scoped strictly by `workspace_id` — admins cannot export other workspaces' data.
- FR-5: App Home impact section reflects real `impact_metrics` data; no hardcoded sample values.
- FR-6: `/relay ask` does not create a Question, Alert, Draft, or any state-machine record.

---

## Non-Goals (Out of Scope)

- Automated classifier retraining pipeline — export only; retraining is manual.
- Confluence connector or additional docs sources (post-launch).
- SOC 2 audit preparation (post-launch).
- Per-user performance reporting for individual CSMs.

---

## Technical Considerations

- Knowledge entry embeddings use the same embedding pipeline as connector chunks (`embed_chunks()`).
- `/relay ask` runs retrieval synchronously inside the Bolt handler (not Celery) — retrieval should be < 2s.
- App Home stats use aggregation queries — add indexes on `impact_metrics(workspace_id, created_at)` and `feedback_signals(workspace_id, created_at, correction_action)`.
- Edit distance between original draft and sent response: compute Levenshtein distance client-side in the send handler; store in `impact_metrics.draft_edit_distance`.

---

## Success Metrics

- After 10 sent responses, `knowledge_entries` are surfaced in at least 20% of new evidence bundles.
- Admin can export feedback JSONL without engineering help.
- `/relay pulse` returns in < 1 second for workspaces with ≤ 100 accounts.

---

## Open Questions

- Should knowledge_entries be surfaced across all accounts in a workspace or scoped to the account where the original question was asked?
- Should the feedback export require Slack OAuth or is a signed URL acceptable?
- What is the retention policy for `knowledge_entries` and their embeddings?
