# PRD: Plan 4 — Source Connectors + Embedding Pipeline

## Introduction

RELAY needs to retrieve evidence from approved external sources (docs, GitHub) so it can generate cited, trustworthy customer-facing drafts. This plan wires up the connector infrastructure, chunking pipeline, and pgvector retrieval layer. No drafting happens here — this plan stops at "chunks are in the DB and retrievable by semantic search."

**Dependency:** Plans 1–3 merged to main (workspace, account, question, SLA all in place).

---

## Goals

- Define a normalized `Connector` interface that all source types implement.
- Ship one docs connector (Notion OR Google Drive — pick one for v1).
- Ship a GitHub connector (issues, PRs, releases, selected markdown docs).
- Chunk and embed source content; store vectors in `knowledge_chunks` with `embedding_model`, `embedding_dims`, `content_hash`.
- Workspace-safe vector search: prefilter by `workspace_id` before similarity search.
- Retrieval logs written for every search so drafting can cite sources.

---

## User Stories

### US-001: Add pgvector extension and knowledge tables migration
**Description:** As a developer, I need the vector database infrastructure and knowledge tables in place before any embedding can be stored.

**Acceptance Criteria:**
- [x] Enable `pgvector` extension in a new Alembic migration (`0004_plan4_connectors.py`)
- [x] `source_connectors` table: `workspace_id`, `connector_type` (enum: `notion`|`google_drive`|`github`), `config` (jsonb), `encrypted_credentials` (bytes), `encrypted_credentials_nonce` (bytes/12), `sync_status`, `last_synced_at`, `disconnected_at`
- [x] `source_documents` table: `workspace_id`, `connector_id` (FK), `external_id`, `title`, `url`, `content_hash`, `provider_updated_at`, `last_synced_at`
- [x] `knowledge_chunks` table: `workspace_id`, `source_document_id` (FK nullable), `knowledge_entry_id` (FK nullable), `chunk_index`, `content` (text), `embedding` (vector(1536)), `embedding_model`, `embedding_dims`, `content_hash`, `created_at`
- [x] `retrieval_logs` table: `draft_id` (FK nullable), `workspace_id`, `sources_used` (jsonb), `query`, `retrieved_at`
- [x] RLS policies on all four tables (same pattern as existing tenant tables)
- [x] ORM models added to `relay/db/models.py` for all four tables
- [ ] Migration runs cleanly: `alembic upgrade head`
- [ ] Typecheck passes

### US-002: Connector interface + registry
**Description:** As a developer, I need a normalized Connector base class that all source types implement, so SLA/drafting code never needs to know which provider is connected.

**Acceptance Criteria:**
- [ ] `relay/connectors/base.py` defines abstract `Connector` with methods: `sync(workspace_id)`, `search(workspace_id, query, top_k)`, `citation(chunk)`, `disconnect(workspace_id)`, `purge(workspace_id)`
- [ ] `relay/connectors/__init__.py` exports a `get_connector(connector_type)` factory
- [ ] `ConnectorType` enum added to `relay/db/models.py`: `notion`, `google_drive`, `github`
- [ ] Unit tests for factory: valid types return correct class, invalid type raises `ValueError`
- [ ] Typecheck passes

### US-003: Docs connector — Google Drive (v1 docs source)
**Description:** As an admin, I want to connect a Google Drive folder so RELAY can index approved docs and use them as evidence in customer responses.

**Acceptance Criteria:**
- [ ] `relay/connectors/google_drive.py` implements `Connector` base
- [ ] OAuth flow: admin visits `/relay/connectors/google_drive/connect`, completes OAuth, token stored encrypted in `source_connectors`
- [ ] Sync: fetch pages/documents from a configured folder ID, store one `source_documents` row per doc (upsert on `external_id`)
- [ ] Content is chunked (800 tokens, 100-token overlap) before embedding
- [ ] `last_synced_at` and `content_hash` updated on sync; unchanged docs are skipped
- [ ] Disconnect: sets `disconnected_at` on the connector row
- [ ] Purge: deletes all `knowledge_chunks` and `source_documents` for this connector
- [ ] Unit tests for chunk logic (input → expected chunk count and boundaries)
- [ ] Typecheck passes

### US-004: GitHub connector
**Description:** As an admin, I want to connect selected GitHub repositories so RELAY can cite issue status, PR titles, release notes, and changelogs in customer responses.

**Acceptance Criteria:**
- [ ] `relay/connectors/github.py` implements `Connector` base
- [ ] GitHub token stored encrypted in `source_connectors`; token entered by admin via `/relay settings`
- [ ] Sync: fetch open+closed issues, PRs, releases, and selected markdown docs from configured repo list; one `source_documents` row per item
- [ ] Each item chunked and embedded; chunks include `title`, `url`, `status`, `labels`, `updated_at` in metadata stored in `config` jsonb
- [ ] `search()` returns top-k chunks by cosine similarity filtered by `workspace_id`
- [ ] `citation()` returns: `{title, url, status, updated_at, excerpt}`
- [ ] Stale flag: chunks not refreshed in > 48h get a `stale=true` field in citation output
- [ ] Unit tests: mock GitHub API, verify chunking and citation output format
- [ ] Typecheck passes

### US-005: Embedding pipeline (shared across connectors)
**Description:** As a developer, I need a shared embedding utility that connectors call to turn text chunks into vectors stored in `knowledge_chunks`.

**Acceptance Criteria:**
- [ ] `relay/connectors/embeddings.py` defines `embed_chunks(workspace_id, chunks, connector_id, source_document_id)` async function
- [ ] Uses Voyage or OpenAI embedding API (configurable via `EMBEDDING_PROVIDER` env var: `voyage`|`openai`)
- [ ] Stores `embedding_model`, `embedding_dims`, `content_hash` on each chunk
- [ ] Idempotent: skip re-embedding if `content_hash` is unchanged
- [ ] Celery task `relay/worker/connector_tasks.py`: `sync_connector(workspace_id, connector_id)` triggers sync + embed
- [ ] Unit tests with mocked embedding API
- [ ] Typecheck passes

### US-006: Tenant-safe semantic search
**Description:** As a developer, I need a `retrieve(workspace_id, query, top_k)` function that finds the most relevant chunks for a given query without ever crossing workspace boundaries.

**Acceptance Criteria:**
- [ ] `relay/connectors/retrieval.py` implements `retrieve(workspace_id, query, top_k=5)` async function
- [ ] Always prefilters by `workspace_id` before vector similarity (pgvector cosine distance)
- [ ] Returns list of `RetrievedChunk` dataclasses: `{chunk_id, source_document_id, content, embedding_model, embedding_dims, citation}`
- [ ] Writes a `retrieval_logs` row per call (query, sources_used jsonb, retrieved_at)
- [ ] Unit tests: verify workspace_id filter is always applied (separate workspace data must not appear in results)
- [ ] Typecheck passes

### US-007: Sync admin command + App Home connector status
**Description:** As an admin, I want to see which connectors are connected, their last sync time, and be able to trigger a manual sync from the App Home.

**Acceptance Criteria:**
- [ ] App Home (relay/slack/home.py) gains a "Connected Sources" section showing: connector type, sync status, last synced at, staleness warning if > 24h
- [ ] `/relay settings` slash command shows connector list and a "Connect" link for unconnected types
- [ ] Celery Beat schedule added for `sync_all_connectors` task (every 6 hours)
- [ ] `sync_all_connectors` loops over all active `source_connectors` and enqueues `sync_connector` per row
- [ ] Typecheck passes

---

## Functional Requirements

- FR-1: All four new tables have RLS policies matching the existing pattern.
- FR-2: `Connector.purge()` removes all `knowledge_chunks` and `source_documents` for the workspace+connector — verified by a test.
- FR-3: Vector search always applies `workspace_id = :wid` filter before similarity ranking.
- FR-4: Chunks include `content_hash` — re-sync skips unchanged content.
- FR-5: Embedding model and dims stored per chunk so model migrations don't corrupt existing vectors.
- FR-6: Citations include freshness timestamp and a staleness flag (> 48h since sync).
- FR-7: Connector credentials encrypted with AES-256-GCM (same pattern as workspace tokens).

---

## Non-Goals (Out of Scope)

- Notion connector — Google Drive ships first; Notion is post-launch.
- Salesforce document connector — not in scope.
- Live Slack cross-channel search — retrieval is from pre-ingested vectors only.
- Per-workspace custom embedding models — single global provider in v1.
- Embedding cost tracking or billing.

---

## Technical Considerations

- pgvector: use `vector(1536)` column type; ensure extension is enabled before migration runs.
- Chunking: 800-token chunks with 100-token overlap. Use `tiktoken` for token counting.
- Cosine distance in pgvector: `<=>` operator. Create `ivfflat` index on `knowledge_chunks(embedding)` with `lists=100`.
- Google Drive OAuth: standard OAuth2 flow via `google-auth` library. Store access + refresh tokens encrypted.
- GitHub: use PyGitHub or raw REST. Personal access token in v1; GitHub App post-launch.
- Embedding API rate limits: batch embed in groups of 20 chunks; add retry with exponential backoff.

---

## Success Metrics

- Admin can connect Google Drive and GitHub without engineering help.
- Sync runs automatically every 6 hours.
- `retrieve()` returns top-5 relevant chunks in < 500ms P95 for a workspace with 10k chunks.
- Zero cross-workspace data leakage (verified by test).

---

## Open Questions

- Voyage vs OpenAI embeddings — which provider first? (Voyage recommended for retrieval quality.)
- Google Drive: folder ID configured via env var or DB setting?
- Should partial sync failures (e.g., one doc 403'd) abort the whole sync or skip and continue?
