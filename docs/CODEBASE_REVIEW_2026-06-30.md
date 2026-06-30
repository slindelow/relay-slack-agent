# RELAY Codebase Review - 2026-06-30

Scope: repository-wide security and efficiency review after the live beta/HubSpot work. No product code was changed in this pass.

Validation:
- `uv run pytest -q` -> 327 passed, 34 skipped, 1 warning.
- `uv run python -m compileall -q relay tests classifier` -> passed.
- `git diff --check` -> passed.
- Bare `python` is not on PATH in this shell; use `uv run python`.

## Findings

### P0 - Public MCP HTTP route has no caller authentication

Files:
- `relay/api/main.py:72`
- `relay/context/mcp_server.py:18`
- `relay/context/mcp_server.py:38`
- `relay/context/mcp_server.py:69`
- `relay/context/mcp_server.py:90`

The FastAPI app mounts the MCP server at `/mcp-api/mcp`, and the MCP tool functions accept `workspace_id`, question/account IDs, and optional Slack user IDs directly. I found DNS rebinding host protection, UUID parsing, RLS-scoped sessions, and audit logs, but no authentication or authorization on the public MCP transport itself.

Impact: anyone who can reach the deployment and knows or can obtain workspace/object UUIDs can call context tools. Depending on the tool and guessed IDs, that can expose question excerpts, account context, indexed knowledge, generated drafts, or trigger LLM/draft work. RLS limits cross-workspace reads only after the caller supplies the workspace ID; it does not prove the caller belongs to that workspace.

Suggested fix: put MCP behind explicit auth before exposing it outside internal workers. Good options are a signed internal service token checked by ASGI middleware on `/mcp-api`, Slack bearer-token auth mapped to a RELAY user, or disabling the HTTP mount in production until an auth story exists. Tool calls should derive workspace/actor from credentials where possible, not trust request parameters alone.

### P1 - Browser HubSpot install trusts forgeable Slack team/user query params

Files:
- `relay/commands/settings.py:144`
- `relay/commands/settings.py:155`
- `relay/api/main.py:774`
- `relay/api/main.py:817`
- `relay/api/main.py:846`

The `/relay settings` HubSpot button builds `/hubspot/install?team_id=...&user_id=...`. `/hubspot/install` then checks whether that user ID is an admin in the database and issues a signed HubSpot OAuth state for the workspace. Slack team IDs and user IDs are identifiers, not proof of possession, and this browser path does not require a Slack signature, bearer token, or signed one-time RELAY token.

Impact: if an attacker learns an admin's Slack user ID and team ID, they can start HubSpot OAuth for the victim workspace and connect a HubSpot portal they control. That can poison CRM/account data and may overwrite the workspace's HubSpot connection.

Suggested fix: generate a short-lived signed install token inside the Slack command/action response and include that in the URL, or require the browser path to complete an authenticated Slack OAuth identity check before issuing HubSpot state. At minimum, sign `team_id:user_id:iat:nonce` and verify it at `/hubspot/install`; ideally bind and consume a one-time nonce.

### P1 - Connector resync leaves stale chunks attached to changed documents

Files:
- `relay/connectors/github.py:195`
- `relay/connectors/github.py:222`
- `relay/connectors/github.py:230`
- `relay/connectors/google_drive.py:116`
- `relay/connectors/google_drive.py:142`
- `relay/connectors/google_drive.py:147`

When a GitHub or Google Drive document changes, the connector updates the `SourceDocument.content_hash` and embeds the new chunks, but it does not delete previous `KnowledgeChunk` rows for that document. Since retrieval searches all chunks for the workspace and then joins back to the current `SourceDocument`, old content can continue to be retrieved and cited as if it belonged to the current document.

Impact: retrieval can surface superseded docs, stale issue/PR bodies, or previous Drive file contents in customer-facing draft evidence. Storage and vector search cost also grow every time a document changes.

Suggested fix: before embedding changed content, delete chunks for `(workspace_id, source_document_id)` inside the same transaction, then insert the fresh chunk set. Add regression tests for GitHub and Drive changed-content resync.

### P2 - Slack event ingestion dedup is logged but not enforced

File:
- `relay/worker/tasks.py:44`

`make_dedup_key()` exists, but the worker only logs it. Slack retries and Celery retries can classify the same message multiple times before the unique message constraint rejects the duplicate insert. This is especially wasteful because classification happens before persistence.

Impact: duplicate Slack deliveries can spend extra LLM/classifier calls and create avoidable worker errors. At beta scale this is manageable, but it can become noisy and expensive as registered channels grow.

Suggested fix: use Redis `SET key value NX EX <ttl>` before classification, or first attempt an idempotent DB insert/upsert for `Message` and skip classification if the message already exists. Keep the unique DB constraint as the final guard.

### P2 - GitHub connector materializes full paginated lists before slicing

File:
- `relay/connectors/github.py:64`
- `relay/connectors/github.py:80`
- `relay/connectors/github.py:94`

The connector uses `list(repo.get_issues(state="all"))[:200]`, and similarly for PRs/releases. With PyGithub paginated lists, `list(...)` walks the whole collection before slicing, so repos with large histories may fetch far more than the intended cap.

Impact: slow syncs, higher GitHub API usage, memory pressure, and higher chance of rate-limit failures.

Suggested fix: iterate with `itertools.islice(repo.get_issues(state="all"), 200)` and equivalent caps for PRs/releases. Consider sorting by recently updated if the API supports it for the desired objects.

## Notes

Things that looked strong:
- Workspace-scoped DB sessions set `app.current_workspace_id`, and models consistently carry workspace IDs plus composite same-workspace foreign keys.
- Token storage uses AES-GCM with per-workspace DEK support when KMS is configured.
- Slack request handling goes through Bolt's signing secret verification.
- Admin-only REST endpoints verify Slack bearer tokens with `auth.test`.
- Existing test coverage is broad and fast.
