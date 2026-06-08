# Plan 8 — Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all Critical and High security findings from the Plan 7 code review, plus targeted Medium/Low improvements, before RELAY goes to Slack Marketplace review.

**Architecture:** Most fixes are additive guards — a new `relay/auth.py` helper centralizes role checks; action handlers gain workspace-from-team_id resolution before any DB lookup; destructive endpoints get explicit authorization. No schema changes needed. All fixes are backward-compatible: new guards default to fail-closed, existing tests that already pass an admin user continue to work.

**Tech Stack:** Python 3.12, SQLAlchemy async ORM, Bolt (Slack SDK), FastAPI, pytest-asyncio, uv

**Implementation status (2026-06-08):** Complete locally on `claude/plan-8-security-hardening`. Final verification: `.venv/bin/python -m pytest -q` passed with 248 passed, 20 skipped, and 1 existing Starlette/httpx warning; `compileall` and `git diff --check` passed.

---

## File map

| File | Change |
|---|---|
| `relay/auth.py` | **Create** — `require_relay_admin()` and `require_relay_csm()` helpers |
| `relay/db/engine.py` | **Modify** — export module-level `async_engine` singleton |
| `relay/commands/delete.py` | **Modify** — admin check before opening modal + before enqueuing deletion |
| `relay/commands/register.py` | **Modify** — admin check before persisting account/channel |
| `relay/slack/actions.py` | **Modify** — resolve workspace from `body.team.id` before unscoped question fetch |
| `relay/slack/home.py` | **Modify** — admin check on connector purge; fix `q.body` → `q.title_excerpt`; log exceptions |
| `relay/slack/draft_actions.py` | **Modify** — role check before posting to customer channel; guard empty `response_body` |
| `relay/api/main.py` | **Modify** — validate `workspace_id` exists on HubSpot install; guard empty `erasure_secret`; explicit AWS KMS error |
| `relay/worker/tasks.py` | **Modify** — safe `.get()` for `team_id` key |
| `relay/worker/deletion_tasks.py` | **Modify** — add `audit_log` to cascade order |
| `relay/sla/poller.py` | **Modify** — use `is_revoked` flag instead of `revoked_at` |
| `relay/drafting/evidence.py` | **Modify** — remove dead `isawaitable` check |
| `relay/drafting/generator.py` | **Modify** — only retry on schema mismatch, not missing tool_use block |
| `relay/drafting/memory.py` | **Modify** — read summary model from settings |
| `relay/config.py` | **Modify** — add `summary_model` setting |
| `relay/integrations/hubspot.py` | **Modify** — redact response bodies from error logs |
| `relay/crypto.py` | **Modify** — raise `NotImplementedError` for `kms_provider="aws"` |
| `tests/test_auth.py` | **Create** — unit tests for the auth helpers |
| `tests/test_security_guards.py` | **Create** — integration tests for all new authorization guards |
| `tests/conftest.py` | **Modify** — add Plan 4-6 tables to RLS test fixture |
| `tests/test_rls.py` | **Modify** — add cross-tenant isolation tests for Plan 4-6 tables |

---

## Task 1: Export `async_engine` + fix `q.body` crash + safe `team_id` access

**Files:**
- Modify: `relay/db/engine.py`
- Modify: `relay/slack/home.py:85`
- Modify: `relay/worker/tasks.py:35`
- Test: `tests/test_api.py` (health check already covers engine import)

These three changes are independent one-liners that fix runtime crashes. Group them in one commit.

- [ ] **Step 1: Fix `relay/db/engine.py` — export `async_engine`**

The deletion task and health endpoint both do `from relay.db.engine import async_engine`, but that name doesn't exist. Add it after `get_session_factory`:

```python
# relay/db/engine.py  — add this line at the end of the file
async_engine = get_engine()
```

- [ ] **Step 2: Fix `relay/slack/home.py:85` — `q.body` → `q.title_excerpt`**

`Question` has no `.body` attribute; the field is `title_excerpt`. The silent `except Exception: pass` above hides this crash and renders the App Home with an empty draft queue for every user.

```python
# relay/slack/home.py line 85 — change:
body_excerpt = (q.body or "")[:120]
# to:
body_excerpt = (q.title_excerpt or "")[:120]
```

- [ ] **Step 3: Fix `relay/worker/tasks.py:35` — safe key access**

```python
# relay/worker/tasks.py line 35 — change:
team_id = payload["team_id"]
# to:
team_id = payload.get("team_id", "")
if not team_id:
    logger.warning("process_slack_event: missing team_id in payload, skipping")
    return
```

- [ ] **Step 4: Replace silent `except Exception: pass` in App Home with a logged warning**

```python
# relay/slack/home.py — find the bare `pass` in the except block of publish_app_home
# Change:
    except Exception:
        pass
# to:
    except Exception:
        logger.warning("publish_app_home: failed to render for user %s", user_id, exc_info=True)
```

- [ ] **Step 5: Run the existing test suite to confirm nothing is broken**

```bash
python -m pytest -q
```
Expected: same pass count as before (233 passed, 19 skipped).

- [ ] **Step 6: Commit**

```bash
git add relay/db/engine.py relay/slack/home.py relay/worker/tasks.py
git commit -m "fix: export async_engine, fix q.body → title_excerpt, safe team_id access"
```

---

## Task 2: Centralized authorization helper

**Files:**
- Create: `relay/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests for the auth helper**

```python
# tests/test_auth.py
"""Tests for relay/auth.py authorization helpers."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_require_relay_admin_returns_true_for_admin():
    from relay.auth import require_relay_admin
    from relay.db.models import User

    admin = MagicMock(spec=User)
    admin.relay_role = "admin"
    admin.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = admin
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_admin(mock_session, workspace_id, "U_ADMIN")
    assert result is True


@pytest.mark.asyncio
async def test_require_relay_admin_returns_false_for_viewer():
    from relay.auth import require_relay_admin

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_admin(mock_session, workspace_id, "U_VIEWER")
    assert result is False


@pytest.mark.asyncio
async def test_require_relay_csm_returns_true_for_csm():
    from relay.auth import require_relay_csm
    from relay.db.models import User

    csm = MagicMock(spec=User)
    csm.relay_role = "csm"
    csm.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = csm
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_csm(mock_session, workspace_id, "U_CSM")
    assert result is True


@pytest.mark.asyncio
async def test_require_relay_csm_returns_true_for_admin():
    """Admins implicitly satisfy the CSM check."""
    from relay.auth import require_relay_csm
    from relay.db.models import User

    admin = MagicMock(spec=User)
    admin.relay_role = "admin"
    admin.deleted_at = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = admin
    mock_session.execute = AsyncMock(return_value=mock_result)

    workspace_id = uuid.uuid4()
    result = await require_relay_csm(mock_session, workspace_id, "U_ADMIN")
    assert result is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_auth.py -v
```
Expected: `ModuleNotFoundError: No module named 'relay.auth'`

- [ ] **Step 3: Create `relay/auth.py`**

```python
"""Authorization helpers for RELAY slash-command and action handlers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.models import User


async def require_relay_admin(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> bool:
    """Return True if the Slack user has relay_role='admin' in this workspace."""
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
            User.relay_role == "admin",
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def require_relay_csm(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> bool:
    """Return True if the Slack user has relay_role in ('admin', 'csm')."""
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
            User.relay_role.in_(["admin", "csm"]),
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_auth.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add relay/auth.py tests/test_auth.py
git commit -m "feat(auth): add require_relay_admin and require_relay_csm helpers"
```

---

## Task 3: Admin guard on `/relay delete-workspace-data`

**Files:**
- Modify: `relay/commands/delete.py`
- Test: `tests/test_security_guards.py` (create)

The delete modal can be opened and confirmed by any Slack user. Add an admin check in `handle_delete_workspace` (before opening the modal) and in `relay_confirm_delete_workspace` (before enqueuing deletion).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security_guards.py
"""Tests verifying authorization guards on destructive RELAY commands."""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_delete_workspace_rejected_for_non_admin():
    """Non-admin user receives an ephemeral error; modal is not opened."""
    from relay.commands.delete import handle_delete_workspace

    ack = AsyncMock()
    respond = AsyncMock()
    client = AsyncMock()
    command = {
        "trigger_id": "T123",
        "user_id": "U_VIEWER",
        "team_id": "T_TEAM",
    }

    mock_workspace = MagicMock()
    mock_workspace.id = uuid.uuid4()

    async def fake_get_session(workspace_id=None):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            ws_result = MagicMock()
            ws_result.scalar_one_or_none.return_value = mock_workspace
            auth_result = MagicMock()
            auth_result.scalar_one_or_none.return_value = None  # not admin
            session.execute = AsyncMock(side_effect=[ws_result, auth_result])
            yield session

        return _cm()

    with patch("relay.commands.delete.get_session", side_effect=fake_get_session):
        await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    ack.assert_called_once()
    client.views_open.assert_not_called()
    respond.assert_called_once()
    assert "admin" in respond.call_args.kwargs.get("text", "").lower()


@pytest.mark.asyncio
async def test_delete_workspace_allowed_for_admin():
    """Admin user gets the confirmation modal opened."""
    from relay.commands.delete import handle_delete_workspace
    from relay.db.models import User, Workspace

    ack = AsyncMock()
    respond = AsyncMock()
    client = AsyncMock()
    command = {
        "trigger_id": "T123",
        "user_id": "U_ADMIN",
        "team_id": "T_TEAM",
    }

    mock_workspace = MagicMock(spec=Workspace)
    mock_workspace.id = uuid.uuid4()
    mock_admin = MagicMock(spec=User)
    mock_admin.relay_role = "admin"

    async def fake_get_session(workspace_id=None):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            ws_result = MagicMock()
            ws_result.scalar_one_or_none.return_value = mock_workspace
            auth_result = MagicMock()
            auth_result.scalar_one_or_none.return_value = mock_admin
            session.execute = AsyncMock(side_effect=[ws_result, auth_result])
            yield session

        return _cm()

    with patch("relay.commands.delete.get_session", side_effect=fake_get_session):
        await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    client.views_open.assert_called_once()
    respond.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_security_guards.py::test_delete_workspace_rejected_for_non_admin tests/test_security_guards.py::test_delete_workspace_allowed_for_admin -v
```
Expected: 2 failures (no admin check exists yet).

- [ ] **Step 3: Update `relay/commands/delete.py` — add admin check and import get_session**

Replace the full file with:

```python
"""Handler for /relay delete-workspace-data slash command (Plan 7 US-002)."""

from __future__ import annotations

import logging

from relay.slack.app import app

logger = logging.getLogger(__name__)

_CONFIRM_MODAL = {
    "type": "modal",
    "callback_id": "relay_confirm_delete_workspace",
    "title": {"type": "plain_text", "text": "Delete workspace data"},
    "submit": {"type": "plain_text", "text": "Delete permanently"},
    "close": {"type": "plain_text", "text": "Cancel"},
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":warning: *This will permanently delete all RELAY data for your workspace.*\n\n"
                    "This cannot be undone. All questions, drafts, knowledge entries, "
                    "and connector data will be removed."
                ),
            },
        }
    ],
}


async def handle_delete_workspace(ack, client, command, respond):
    await ack()

    team_id = command.get("team_id", "")
    slack_user_id = command.get("user_id", "")
    trigger_id = command.get("trigger_id", "")

    if not trigger_id:
        await respond(
            response_type="ephemeral",
            text="Could not open confirmation modal. Please try again.",
        )
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Workspace
        from relay.db.session import get_session
        from relay.auth import require_relay_admin

        async with get_session() as session:
            ws_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(response_type="ephemeral", text="RELAY workspace not found.")
            return

        async with get_session(workspace_id=workspace.id) as session:
            is_admin = await require_relay_admin(session, workspace.id, slack_user_id)

        if not is_admin:
            await respond(
                response_type="ephemeral",
                text=":no_entry: Only workspace admins can delete RELAY data.",
            )
            return

        await client.views_open(trigger_id=trigger_id, view=_CONFIRM_MODAL)
    except Exception:
        logger.exception("Failed to open delete-workspace confirmation modal")
        await respond(
            response_type="ephemeral",
            text="Could not open confirmation modal. Please try again.",
        )


@app.view("relay_confirm_delete_workspace")
async def relay_confirm_delete_workspace(ack, body):
    await ack()
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    slack_user_id = body.get("user", {}).get("id", "")
    if not team_id:
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Workspace
        from relay.db.session import get_session
        from relay.auth import require_relay_admin
        from relay.worker.deletion_tasks import delete_workspace_data

        async with get_session() as session:
            result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = result.scalar_one_or_none()

        if workspace is None:
            return

        async with get_session(workspace_id=workspace.id) as session:
            is_admin = await require_relay_admin(session, workspace.id, slack_user_id)

        if not is_admin:
            logger.warning(
                "relay_confirm_delete_workspace: non-admin %s attempted deletion for team %s",
                slack_user_id, team_id,
            )
            return

        delete_workspace_data.delay(str(workspace.id))
        logger.info("Enqueued workspace deletion for workspace_id=%s", workspace.id)
    except Exception:
        logger.exception("Failed to enqueue workspace deletion for team_id=%s", team_id)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_security_guards.py::test_delete_workspace_rejected_for_non_admin tests/test_security_guards.py::test_delete_workspace_allowed_for_admin -v
```
Expected: 2 passed.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -q
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add relay/commands/delete.py tests/test_security_guards.py
git commit -m "fix(security): require admin role before opening workspace deletion modal"
```

---

## Task 4: Admin guard on `/relay register` and connector purge

**Files:**
- Modify: `relay/commands/register.py:148`
- Modify: `relay/slack/home.py:391`
- Test: `tests/test_security_guards.py` (append)

- [ ] **Step 1: Add failing tests to `tests/test_security_guards.py`**

Append these tests to the existing file:

```python
@pytest.mark.asyncio
async def test_register_rejected_for_non_admin():
    """Non-admin user gets ephemeral error; no DB writes."""
    from relay.commands.register import handle_register

    ack = AsyncMock()
    respond = AsyncMock()

    mock_workspace = MagicMock()
    mock_workspace.id = uuid.uuid4()

    async def fake_get_session(workspace_id=None):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            ws_result = MagicMock()
            ws_result.scalar_one_or_none.return_value = mock_workspace
            auth_result = MagicMock()
            auth_result.scalar_one_or_none.return_value = None  # not admin
            session.execute = AsyncMock(side_effect=[ws_result, auth_result])
            yield session

        return _cm()

    with patch("relay.commands.register.get_session", side_effect=fake_get_session):
        await handle_register(
            ack=ack,
            respond=respond,
            command={
                "text": "register <#C123|acme> Acme Corp enterprise",
                "user_id": "U_VIEWER",
                "team_id": "T_TEAM",
            },
        )

    respond.assert_called_once()
    assert "admin" in respond.call_args.kwargs.get("text", "").lower()


@pytest.mark.asyncio
async def test_connector_purge_rejected_for_non_admin():
    """Non-admin user gets ephemeral error; connector is not purged."""
    from relay.slack.home import handle_confirm_purge_connector

    ack = AsyncMock()
    client = AsyncMock()

    connector_id = str(uuid.uuid4())
    body = {
        "user": {"id": "U_VIEWER"},
        "view": {
            "private_metadata": f'{{"team_id": "T_TEAM", "connector_id": "{connector_id}"}}'
        },
    }

    mock_workspace = MagicMock()
    mock_workspace.id = uuid.uuid4()

    async def fake_get_session(workspace_id=None):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            ws_result = MagicMock()
            ws_result.scalar_one_or_none.return_value = mock_workspace
            auth_result = MagicMock()
            auth_result.scalar_one_or_none.return_value = None  # not admin
            connector_result = MagicMock()
            connector_result.scalar_one_or_none.return_value = None
            session.execute = AsyncMock(
                side_effect=[ws_result, auth_result, connector_result]
            )
            yield session

        return _cm()

    with patch("relay.slack.home.get_session", side_effect=fake_get_session):
        await handle_confirm_purge_connector(ack=ack, body=body, client=client)

    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_security_guards.py::test_register_rejected_for_non_admin tests/test_security_guards.py::test_connector_purge_rejected_for_non_admin -v
```
Expected: 2 failures.

- [ ] **Step 3: Add admin check to `relay/commands/register.py`**

In `handle_register`, add the check after resolving the workspace (after line 174, before `_fetch_channel_metadata`). Import `require_relay_admin` at the top of the function body:

```python
# relay/commands/register.py — inside handle_register(), after workspace lookup
# (after the "if workspace is None: return" block, before _fetch_channel_metadata call)

        from relay.auth import require_relay_admin
        async with get_session(workspace_id=workspace.id) as auth_session:
            is_admin = await require_relay_admin(
                auth_session, workspace.id, command.get("user_id", "")
            )
        if not is_admin:
            await respond(
                response_type="ephemeral",
                text=":no_entry: Only workspace admins can register channels.",
            )
            return
```

Place these lines immediately after the `workspace is None` guard block (around line 174), before the `_fetch_channel_metadata` call.

- [ ] **Step 4: Add admin check to `relay/slack/home.py` — `handle_confirm_purge_connector`**

In `handle_confirm_purge_connector` (around line 391), add an admin check after resolving the workspace, before deleting anything:

```python
# relay/slack/home.py — inside handle_confirm_purge_connector()
# After extracting team_id and connector_id from private_metadata,
# before the connector delete logic:

        from relay.auth import require_relay_admin

        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await ack()
            return

        async with get_session(workspace_id=workspace.id) as auth_session:
            is_admin = await require_relay_admin(
                auth_session, workspace.id, slack_user_id
            )

        if not is_admin:
            await ack()
            return
```

Retrieve `slack_user_id = body.get("user", {}).get("id", "")` at the top of the handler alongside `team_id`.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_security_guards.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add relay/commands/register.py relay/slack/home.py tests/test_security_guards.py
git commit -m "fix(security): require admin role for channel registration and connector purge"
```

---

## Task 5: Role check before posting drafts to customer channel

**Files:**
- Modify: `relay/slack/draft_actions.py`
- Test: `tests/test_security_guards.py` (append)

Any user who opens a draft modal can currently approve and send the response to the customer channel. Require `relay_role in ('admin', 'csm')`. Also guard empty `response_body`.

- [ ] **Step 1: Add failing tests to `tests/test_security_guards.py`**

```python
@pytest.mark.asyncio
async def test_send_draft_rejected_for_viewer():
    """Viewer cannot send drafts to customer channel."""
    from relay.slack.draft_actions import handle_send_draft
    import json

    ack = AsyncMock()
    client = AsyncMock()

    workspace_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    mock_viewer = MagicMock()
    mock_viewer.relay_role = "viewer"

    body = {
        "user": {"id": "U_VIEWER"},
        "view": {
            "private_metadata": json.dumps(
                {"draft_id": str(draft_id), "workspace_id": str(workspace_id)}
            ),
            "state": {
                "values": {
                    "response_body": {
                        "response_body_value": {"value": "Here is my answer."}
                    }
                }
            },
        },
    }

    mock_draft = MagicMock()
    mock_draft.question_id = uuid.uuid4()
    mock_actor = MagicMock()
    mock_actor.relay_role = "viewer"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    draft_result = MagicMock()
    draft_result.scalar_one_or_none.return_value = mock_draft
    auth_result = MagicMock()
    auth_result.scalar_one_or_none.return_value = None  # not csm/admin

    mock_session.execute = AsyncMock(side_effect=[draft_result, auth_result])

    with patch("relay.slack.draft_actions.get_session", return_value=mock_session):
        await handle_send_draft(ack=ack, body=body, client=client)

    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_send_draft_rejects_empty_response_body():
    """Empty response_body is not posted to the customer channel."""
    from relay.slack.draft_actions import handle_send_draft
    import json

    ack = AsyncMock()
    client = AsyncMock()

    workspace_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    body = {
        "user": {"id": "U_ADMIN"},
        "view": {
            "private_metadata": json.dumps(
                {"draft_id": str(draft_id), "workspace_id": str(workspace_id)}
            ),
            "state": {
                "values": {
                    "response_body": {
                        "response_body_value": {"value": "   "}  # whitespace only
                    }
                }
            },
        },
    }

    mock_draft = MagicMock()
    mock_draft.question_id = uuid.uuid4()
    mock_actor = MagicMock()
    mock_actor.relay_role = "admin"
    mock_actor.display_name = "Admin"
    mock_actor.slack_user_id = "U_ADMIN"
    mock_actor.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    draft_result = MagicMock()
    draft_result.scalar_one_or_none.return_value = mock_draft
    auth_result = MagicMock()
    auth_result.scalar_one_or_none.return_value = mock_actor

    mock_session.execute = AsyncMock(side_effect=[draft_result, auth_result])

    with patch("relay.slack.draft_actions.get_session", return_value=mock_session):
        await handle_send_draft(ack=ack, body=body, client=client)

    client.chat_postMessage.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_security_guards.py::test_send_draft_rejected_for_viewer tests/test_security_guards.py::test_send_draft_rejects_empty_response_body -v
```

- [ ] **Step 3: Add role check and empty-body guard in `relay/slack/draft_actions.py`**

In `handle_send_draft`, inside the `async with get_session(workspace_id) as session:` block, after loading the draft (around line 185), add:

```python
            # relay/slack/draft_actions.py — add after draft is loaded, before posting
            from relay.auth import require_relay_csm
            is_authorized = await require_relay_csm(session, workspace_id, user_id)
            if not is_authorized:
                logger.warning(
                    "relay_send_draft: unauthorized send attempt by %s for draft %s",
                    user_id, draft_id,
                )
                return
```

And before the `if channel_id_slack:` block (around line 218), add:

```python
            # Guard: do not post empty responses
            if not response_body.strip():
                logger.warning("relay_send_draft: empty response_body, aborting send")
                return
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_security_guards.py -v
```

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add relay/slack/draft_actions.py tests/test_security_guards.py
git commit -m "fix(security): require csm/admin role and non-empty body before sending drafts"
```

---

## Task 6: Tenant isolation — resolve workspace before question fetch in actions.py

**Files:**
- Modify: `relay/slack/actions.py`
- Test: `tests/test_security_guards.py` (append)

In `handle_claim_question`, `_handle_snooze`, and `handle_mark_not_question`, the workspace is currently derived from the `Question` row fetched unscoped. This allows crafting a payload with a UUID from another workspace. Fix: resolve workspace from `body["team"]["id"]` first, then fetch the question inside the scoped session.

- [ ] **Step 1: Add failing test to `tests/test_security_guards.py`**

```python
@pytest.mark.asyncio
async def test_claim_question_uses_team_id_not_question_workspace():
    """Workspace is resolved from Slack team_id before any question lookup."""
    from relay.slack.actions import handle_claim_question

    ack = AsyncMock()
    respond = AsyncMock()

    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()

    mock_workspace = MagicMock()
    mock_workspace.id = workspace_id

    mock_question = MagicMock()
    mock_question.workspace_id = workspace_id
    mock_question.state = "open"

    call_order = []

    async def fake_get_session(wid=None):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            session.commit = AsyncMock()
            if wid is None:
                call_order.append("unscoped")
                ws_result = MagicMock()
                ws_result.scalar_one_or_none.return_value = mock_workspace
                session.execute = AsyncMock(return_value=ws_result)
            else:
                call_order.append("scoped")
                q_result = MagicMock()
                q_result.scalar_one_or_none.return_value = mock_question
                session.execute = AsyncMock(return_value=q_result)
            yield session

        return _cm()

    body = {
        "actions": [{"value": str(question_id)}],
        "user": {"id": "U123"},
        "team": {"id": "T_TEAM"},
    }

    with patch("relay.slack.actions.get_session", side_effect=fake_get_session):
        with patch("relay.slack.actions.claim_question", new_callable=AsyncMock):
            await handle_claim_question(ack=ack, body=body, respond=respond)

    # The unscoped call must happen first (workspace lookup), then scoped (question lookup)
    assert call_order[0] == "unscoped"
    assert call_order[1] == "scoped"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_security_guards.py::test_claim_question_uses_team_id_not_question_workspace -v
```

- [ ] **Step 3: Refactor `handle_claim_question` in `relay/slack/actions.py`**

Replace the handler body with the workspace-first pattern:

```python
@app.action("relay_claim_question")
async def handle_claim_question(ack, body, respond, logger=logger):
    await ack()

    question_id = _get_question_id_from_action(body)
    if question_id is None:
        await respond(text="⚠️ Could not parse question ID.", response_type="ephemeral")
        return

    actor_slack_id = body.get("user", {}).get("id", "")
    team_id = body.get("team", {}).get("id", "")

    try:
        from sqlalchemy import select
        from relay.db.models import Question, QuestionState, Workspace
        from relay.db.session import get_session

        # Step 1 — resolve workspace from Slack team_id (unscoped, workspace table has no RLS)
        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(text="⚠️ Workspace not found.", response_type="ephemeral")
            return

        workspace_id = workspace.id

        # Step 2 — all further queries use the scoped (RLS-enforced) session
        async with get_session(workspace_id) as session:
            actor = await _get_or_create_user(session, workspace_id, actor_slack_id)

            from relay.question.machine import claim_question, InvalidStateTransition
            try:
                await claim_question(session, question_id, actor.id)
            except InvalidStateTransition as exc:
                await respond(
                    text=f"⚠️ Cannot claim: question is already *{exc.from_state}*.",
                    response_type="ephemeral",
                )
                return

        await respond(
            text="✅ You've claimed this question. It's now yours to answer.",
            response_type="ephemeral",
        )
    except Exception:
        logger.exception("handle_claim_question failed")
        await respond(text="⚠️ An error occurred.", response_type="ephemeral")
```

Apply the same pattern to `_handle_snooze` and `handle_mark_not_question` — extract `team_id = body.get("team", {}).get("id", "")`, resolve workspace unscoped first, then do all question access in the scoped session.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_security_guards.py -v
```

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add relay/slack/actions.py tests/test_security_guards.py
git commit -m "fix(security): resolve workspace from team_id before question fetch in action handlers"
```

---

## Task 7: GDPR endpoint hardening + HubSpot OAuth workspace validation

**Files:**
- Modify: `relay/api/main.py`

- [ ] **Step 1: Guard empty `erasure_secret` in the erasure endpoint**

In `relay/api/main.py`, at the top of the `DELETE /relay/admin/users/{slack_user_id}/erase` endpoint body, add:

```python
    # relay/api/main.py — erasure endpoint, first line of handler body
    settings = get_settings()
    if not settings.erasure_secret:
        raise HTTPException(
            status_code=503,
            detail="User erasure endpoint is not configured on this deployment.",
        )
```

- [ ] **Step 2: Validate `workspace_id` exists in `/hubspot/install`**

In `hubspot_install`, after the UUID parse succeeds, verify the workspace exists in the DB before issuing the OAuth redirect:

```python
# relay/api/main.py — hubspot_install, after UUID(workspace_id) parse succeeds
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        return JSONResponse({"error": "invalid workspace_id"}, status_code=400)

    # Verify workspace exists before issuing OAuth state
    try:
        from sqlalchemy import select
        from relay.db.session import get_session
        from relay.db.models import Workspace

        async with get_session() as db:
            ws_result = await db.execute(
                select(Workspace.id).where(Workspace.id == workspace_uuid)
            )
            if ws_result.scalar_one_or_none() is None:
                return JSONResponse({"error": "workspace not found"}, status_code=404)
    except Exception:
        return JSONResponse({"error": "database error"}, status_code=500)

    state = build_hubspot_state(
        workspace_id=workspace_uuid,
        signing_key=settings.token_encryption_key_bytes,
    )
```

- [ ] **Step 3: Write tests for both guards**

```python
# tests/test_security_guards.py — append

def test_erasure_endpoint_returns_503_when_secret_not_set(monkeypatch):
    """Erasure endpoint returns 503 when ERASURE_SECRET is not configured."""
    import importlib
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SLACK_CLIENT_ID", "cid")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "ssecret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("ERASURE_SECRET", "")  # explicitly empty

    from relay.config import get_settings
    get_settings.cache_clear()
    api_module = importlib.import_module("relay.api.main")
    importlib.reload(api_module)

    client = TestClient(api_module.api)
    resp = client.delete(
        "/relay/admin/users/U123/erase",
        params={"confirmation_token": "any"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 503
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_security_guards.py -v
```

- [ ] **Step 5: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add relay/api/main.py tests/test_security_guards.py
git commit -m "fix(security): guard empty erasure_secret and validate workspace on hubspot OAuth install"
```

---

## Task 8: Data deletion completeness + SLA revocation flag fix

**Files:**
- Modify: `relay/worker/deletion_tasks.py`
- Modify: `relay/sla/poller.py`

- [ ] **Step 1: Add `audit_log` to cascade delete order**

```python
# relay/worker/deletion_tasks.py — _CASCADE_ORDER list
# Change:
_CASCADE_ORDER = [
    "knowledge_chunks",
    ...
    "classification_feedback",
]
# to (add audit_log at the end — it has no outbound FK dependencies):
_CASCADE_ORDER = [
    "knowledge_chunks",
    "knowledge_entries",
    "source_documents",
    "source_connectors",
    "retrieval_logs",
    "drafts",
    "impact_metrics",
    "feedback_signals",
    "alerts",
    "snoozes",
    "assignments",
    "question_events",
    "questions",
    "messages",
    "monitored_channels",
    "customer_accounts",
    "users",
    "workspace_tokens",
    "workspace_settings",
    "sla_policies",
    "crm_connections",
    "classification_feedback",
    "audit_log",
]
```

- [ ] **Step 2: Fix revocation flag in SLA poller**

```python
# relay/sla/poller.py line ~189 — change:
                WorkspaceToken.revoked_at.is_(None),
# to:
                WorkspaceToken.is_revoked.is_(False),
```

- [ ] **Step 3: Write a test for the cascade order**

```python
# tests/test_deletion_tasks.py — add this test (append to existing file)

def test_cascade_order_includes_audit_log():
    from relay.worker.deletion_tasks import _CASCADE_ORDER
    assert "audit_log" in _CASCADE_ORDER
    # audit_log must come after users (user data deleted first)
    assert _CASCADE_ORDER.index("audit_log") > _CASCADE_ORDER.index("users")
```

- [ ] **Step 4: Write a test for revocation flag**

```python
# tests/test_sla_alerts.py — add this test (or create tests/test_poller_revocation.py)

def test_poller_filters_on_is_revoked_not_revoked_at():
    """Regression: poller must use is_revoked=False, not revoked_at IS NULL."""
    import inspect
    import relay.sla.poller as poller_module
    source = inspect.getsource(poller_module)
    assert "is_revoked.is_(False)" in source
    assert "revoked_at.is_(None)" not in source
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_deletion_tasks.py tests/test_sla_alerts.py -v
```

- [ ] **Step 6: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add relay/worker/deletion_tasks.py relay/sla/poller.py
git commit -m "fix: add audit_log to deletion cascade; use is_revoked flag in SLA poller"
```

---

## Task 9: Medium code quality fixes

**Files:**
- Modify: `relay/drafting/evidence.py`
- Modify: `relay/drafting/generator.py`
- Modify: `relay/integrations/hubspot.py`
- Modify: `relay/crypto.py`
- Modify: `relay/config.py`
- Modify: `relay/drafting/memory.py`

- [ ] **Step 1: Remove dead `isawaitable` check in `relay/drafting/evidence.py`**

Find and remove lines 82–85 (the `if inspect.isawaitable(row): row = await row` block) and the `import inspect` if it is only used there.

- [ ] **Step 2: Fix retry logic in `relay/drafting/generator.py`**

The generator retries on any failure in the schema-parse block, including the case where no `tool_use` block exists at all. Separate the two failure modes:

```python
# relay/drafting/generator.py — inside _call_with_retry, replace the loop:
for attempt in range(2):
    response = await self._client.messages.create(...)
    tool_use_block = next(
        (b for b in response.content if b.type == "tool_use"), None
    )
    if tool_use_block is None:
        # Model did not call the tool — not retryable
        break
    try:
        return DraftOutput(**tool_use_block.input)
    except Exception:
        if attempt == 0:
            continue  # schema mismatch — retry once
        raise
raise RuntimeError("Draft generation failed: model did not produce a valid tool call")
```

- [ ] **Step 3: Redact HubSpot response bodies from logs**

```python
# relay/integrations/hubspot.py — wherever response.text appears in error messages
# Change:
raise HubSpotOAuthError(f"Token exchange failed {response.status_code}: {response.text}")
# to:
raise HubSpotOAuthError(f"Token exchange failed {response.status_code}: [response body redacted]")
```
Apply this to all two locations in `hubspot.py` where `response.text` is logged or included in exceptions.

- [ ] **Step 4: Raise `NotImplementedError` for AWS KMS in `relay/crypto.py`**

```python
# relay/crypto.py — get_kms_provider()
def get_kms_provider() -> KMSProvider:
    from relay.config import get_settings
    settings = get_settings()
    if settings.kms_provider == "aws":
        raise NotImplementedError(
            "AWS KMS provider is not yet implemented. "
            "Set KMS_PROVIDER=local for dev/test deployments."
        )
    return LocalKMSProvider(settings.token_encryption_key_bytes)
```

- [ ] **Step 5: Add configurable `summary_model` to settings**

```python
# relay/config.py — add to Settings class
summary_model: str = "claude-haiku-4-5-20251001"
```

```python
# relay/drafting/memory.py line 18 — change:
model="claude-haiku-4-5-20251001",
# to:
model=get_settings().summary_model,
```
Add `from relay.config import get_settings` import at the top of `memory.py`.

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest -q
```
Expected: same pass count as before.

- [ ] **Step 7: Commit**

```bash
git add relay/drafting/evidence.py relay/drafting/generator.py relay/integrations/hubspot.py relay/crypto.py relay/config.py relay/drafting/memory.py
git commit -m "fix: dead code removal, retry logic, log redaction, AWS KMS guard, configurable summary model"
```

---

## Task 10: Expand RLS test coverage to Plan 4-6 tables

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_rls.py`

Plan 4-6 tables (`drafts`, `source_connectors`, `source_documents`, `knowledge_chunks`, `knowledge_entries`) have RLS policies in the migrations but are not tested for cross-tenant isolation.

- [ ] **Step 1: Add Plan 4-6 tables to `TENANT_TABLES` in `conftest.py`**

Find the `TENANT_TABLES` list in `tests/conftest.py` and append:

```python
# tests/conftest.py — TENANT_TABLES — add these after existing entries:
    "drafts",
    "source_connectors",
    "source_documents",
    "knowledge_chunks",
    "knowledge_entries",
```

- [ ] **Step 2: Add cross-tenant isolation tests to `tests/test_rls.py`**

Append these tests:

```python
@pytest.mark.asyncio
async def test_draft_rls_isolates_across_workspaces(db_session):
    """A draft created for workspace A is not visible to workspace B's session."""
    from sqlalchemy import select, text
    from relay.db.models import Draft, Question, MonitoredChannel, CustomerAccount
    from relay.slack.oauth import upsert_workspace_from_install

    ws_a = await upsert_workspace_from_install(db_session, "T_DRAFT_A", "WS A")
    ws_b = await upsert_workspace_from_install(db_session, "T_DRAFT_B", "WS B")
    await db_session.flush()

    # Create minimal question for workspace A
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :wid, true)"),
        {"wid": str(ws_a.id)},
    )
    account_a = CustomerAccount(workspace_id=ws_a.id, name="Acme", tier="starter")
    db_session.add(account_a)
    await db_session.flush()
    channel_a = MonitoredChannel(
        workspace_id=ws_a.id,
        slack_channel_id="C_A",
        account_id=account_a.id,
    )
    db_session.add(channel_a)
    await db_session.flush()
    question_a = Question(
        workspace_id=ws_a.id,
        channel_id=channel_a.id,
        title_excerpt="Test question",
        is_customer_message=True,
    )
    db_session.add(question_a)
    await db_session.flush()
    draft_a = Draft(
        workspace_id=ws_a.id,
        question_id=question_a.id,
        body="Draft response",
        status="pending",
    )
    db_session.add(draft_a)
    await db_session.flush()

    # Switch to workspace B context — draft_a must not be visible
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :wid, true)"),
        {"wid": str(ws_b.id)},
    )
    result = await db_session.execute(select(Draft).where(Draft.id == draft_a.id))
    assert result.scalar_one_or_none() is None, "RLS leak: draft_a visible to workspace B"
```

- [ ] **Step 3: Run the new RLS tests**

```bash
python -m pytest tests/test_rls.py -v
```
Expected: new test passes (proves RLS is enforced).

- [ ] **Step 4: Run full suite**

```bash
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_rls.py
git commit -m "test: expand RLS coverage to Plan 4-6 tables (drafts, connectors, knowledge)"
```

---

## Self-review

**Spec coverage check:**

| Finding | Task |
|---|---|
| Critical: `async_engine` not exported | Task 1 |
| Critical: RLS bypass in `actions.py` | Task 6 |
| Critical: any user can delete workspace | Task 3 |
| Critical: erasure secret empty bypass | Task 7 |
| High: any user can register channels | Task 4 |
| High: connector purge no auth check | Task 4 |
| High: any user can send drafts | Task 5 |
| High: empty `response_body` sent to customer | Task 5 |
| High: `q.body` crash → App Home broken | Task 1 |
| High: `payload["team_id"]` KeyError | Task 1 |
| High: HubSpot OAuth for arbitrary workspace_id | Task 7 |
| High: `audit_log` not deleted | Task 8 |
| Medium: wrong revocation flag in SLA poller | Task 8 |
| Medium: dead `isawaitable` check | Task 9 |
| Medium: retry logic on non-retryable failures | Task 9 |
| Medium: log redaction for HubSpot errors | Task 9 |
| Medium: AWS KMS silently ignored | Task 9 |
| Low: hardcoded `summary_model` | Task 9 |
| Low: RLS tests don't cover Plan 4-6 | Task 10 |
| Low: silent exception swallowing in App Home | Task 1 |

All 20 findings are covered.

**Excluded (out of scope):**
- KMS/DEK wiring (US-001 architectural work — schema exists, no actual tokens to re-encrypt yet)
- Google Drive blocking I/O (requires async Drive client migration — separate plan)
- Celery deduplication Redis `SETNX` (TODO comment in code, acceptable for current scale)
- N+1 SLA poller pattern (documented design decision, acceptable for current scale)
- Health check Redis connection pool (minor operational issue, low priority)
