"""Tests verifying authorization guards on destructive RELAY commands."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Workspace deletion guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_workspace_rejected_for_non_admin():
    """Non-admin user receives ephemeral error; modal is not opened."""
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

    sessions_created = []

    def fake_get_session(workspace_id=None):
        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            if workspace_id is None:
                ws_result = MagicMock()
                ws_result.scalar_one_or_none.return_value = mock_workspace
                session.execute = AsyncMock(return_value=ws_result)
            else:
                auth_result = MagicMock()
                auth_result.scalar_one_or_none.return_value = None  # not admin
                session.execute = AsyncMock(return_value=auth_result)
            sessions_created.append(workspace_id)
            yield session

        return _cm()

    with patch("relay.db.session.get_session", side_effect=fake_get_session):
        await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    ack.assert_called_once()
    client.views_open.assert_not_called()
    respond.assert_called_once()
    text = respond.call_args.kwargs.get("text", "") or (respond.call_args.args[0] if respond.call_args.args else "")
    assert "admin" in text.lower()


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

    def fake_get_session(workspace_id=None):
        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            if workspace_id is None:
                ws_result = MagicMock()
                ws_result.scalar_one_or_none.return_value = mock_workspace
                session.execute = AsyncMock(return_value=ws_result)
            else:
                auth_result = MagicMock()
                auth_result.scalar_one_or_none.return_value = mock_admin
                session.execute = AsyncMock(return_value=auth_result)
            yield session

        return _cm()

    with patch("relay.db.session.get_session", side_effect=fake_get_session):
        await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    client.views_open.assert_called_once()
    respond.assert_not_called()


# ---------------------------------------------------------------------------
# Register channel guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_rejected_for_non_admin():
    """Non-admin user gets ephemeral error; no DB writes."""
    from relay.commands.register import handle_register

    ack = AsyncMock()
    respond = AsyncMock()

    mock_workspace = MagicMock()
    mock_workspace.id = uuid.uuid4()

    def fake_get_session(workspace_id=None):
        @asynccontextmanager
        async def _cm():
            session = AsyncMock()
            if workspace_id is None:
                ws_result = MagicMock()
                ws_result.scalar_one_or_none.return_value = mock_workspace
                session.execute = AsyncMock(return_value=ws_result)
            else:
                auth_result = MagicMock()
                auth_result.scalar_one_or_none.return_value = None  # not admin
                session.execute = AsyncMock(return_value=auth_result)
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
    text = respond.call_args.kwargs.get("text", "")
    assert "admin" in text.lower()


# ---------------------------------------------------------------------------
# Draft send guards
# ---------------------------------------------------------------------------


def test_customer_response_text_uses_display_name_without_approval_framing():
    from relay.slack.draft_actions import _build_customer_response_text

    actor = MagicMock()
    actor.display_name = "Sofia"
    actor.slack_user_id = "U_ADMIN"

    text = _build_customer_response_text("Here is the answer.", actor)

    assert text == "From Sofia via RELAY:\n\nHere is the answer."
    assert "approval" not in text.lower()
    assert "U_ADMIN" not in text


def test_customer_response_text_falls_back_without_raw_slack_id():
    from relay.slack.draft_actions import _build_customer_response_text

    actor = MagicMock()
    actor.display_name = ""
    actor.slack_user_id = "U_ADMIN"

    text = _build_customer_response_text("Here is the answer.", actor)

    assert text == "From your customer success team via RELAY:\n\nHere is the answer."
    assert "U_ADMIN" not in text


@pytest.mark.asyncio
async def test_send_draft_rejected_for_viewer():
    """Viewer cannot send drafts to customer channel."""
    import json
    from relay.slack.draft_actions import handle_send_draft

    ack = AsyncMock()
    client = AsyncMock()

    workspace_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    question_id = uuid.uuid4()

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
    mock_draft.question_id = question_id
    mock_draft.status = "pending"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    draft_result = MagicMock()
    draft_result.scalar_one_or_none.return_value = mock_draft
    # Auth check: None = not authorized (viewer)
    auth_result = MagicMock()
    auth_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[draft_result, auth_result])

    with patch("relay.slack.draft_actions.get_session", return_value=mock_session):
        await handle_send_draft(ack=ack, body=body, client=client)

    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_send_draft_rejects_empty_response_body():
    """Empty response_body is not posted to the customer channel."""
    import json
    from relay.slack.draft_actions import handle_send_draft
    from relay.db.models import User

    ack = AsyncMock()
    client = AsyncMock()

    workspace_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    question_id = uuid.uuid4()

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
    mock_draft.question_id = question_id
    mock_draft.status = "pending"

    mock_admin = MagicMock(spec=User)
    mock_admin.relay_role = "admin"
    mock_admin.id = uuid.uuid4()
    mock_admin.display_name = "Admin"
    mock_admin.slack_user_id = "U_ADMIN"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    draft_result = MagicMock()
    draft_result.scalar_one_or_none.return_value = mock_draft
    auth_result = MagicMock()
    auth_result.scalar_one_or_none.return_value = mock_admin  # authorized
    # question result, actor result, channel result
    q_result = MagicMock()
    q_result.scalar_one_or_none.return_value = None  # no question needed — empty body guard fires first
    mock_session.execute = AsyncMock(side_effect=[draft_result, auth_result, q_result])

    with patch("relay.slack.draft_actions.get_session", return_value=mock_session):
        await handle_send_draft(ack=ack, body=body, client=client)

    client.chat_postMessage.assert_not_called()


def test_hubspot_install_requires_bearer_admin_token():
    from relay.api.main import api

    client = TestClient(api)
    response = client.get("/hubspot/install", follow_redirects=False)

    assert response.status_code == 401


def test_hubspot_install_uses_authenticated_workspace():
    from relay.api.main import api

    client = TestClient(api)
    workspace_id = uuid.uuid4()
    workspace = MagicMock()
    workspace.id = workspace_id
    admin = MagicMock()
    admin.relay_role = "admin"

    call_count = 0

    def fake_get_session(workspace_id_arg=None):
        nonlocal call_count

        @asynccontextmanager
        async def _cm():
            nonlocal call_count
            session = AsyncMock()
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                # First call: workspace lookup by slack_team_id
                result.scalar_one_or_none.return_value = workspace
            elif call_count == 2:
                # Second call: user lookup for admin check
                result.scalar_one_or_none.return_value = admin
            else:
                # Third call: workspace existence DB check (new guard)
                result.scalar_one_or_none.return_value = workspace.id
            session.execute = AsyncMock(return_value=result)
            yield session

        return _cm()

    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T_TEAM", "user_id": "U_ADMIN"})),
        patch("relay.api.main.get_session", side_effect=fake_get_session),
        patch("relay.api.main.get_settings") as mock_settings,
    ):
        mock_settings.return_value.token_encryption_key_bytes = b"\xaa" * 32
        mock_settings.return_value.hubspot_client_id = "client-id"
        mock_settings.return_value.hubspot_redirect_uri = "https://relay.example.com/hubspot/oauth_redirect"

        response = client.get(
            f"/hubspot/install?workspace_id={workspace_id}",
            headers={"Authorization": "Bearer xoxp-admin"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://app.hubspot.com/oauth/authorize?")


# ---------------------------------------------------------------------------
# GDPR erasure + HubSpot OAuth guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erasure_endpoint_returns_503_when_secret_not_set():
    """Erasure endpoint returns 503 when ERASURE_SECRET is not configured."""
    import relay.api.main as api_module
    from fastapi.testclient import TestClient

    mock_settings = MagicMock()
    mock_settings.erasure_secret = ""

    with patch("relay.api.main.get_settings", return_value=mock_settings):
        client = TestClient(api_module.api, raise_server_exceptions=False)
        resp = client.delete(
            "/relay/admin/users/U123/erase",
            params={"confirmation_token": "any"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_hubspot_install_returns_404_for_unknown_workspace():
    """HubSpot install endpoint returns 404 when workspace_id does not exist."""
    import relay.api.main as api_module
    from fastapi.testclient import TestClient

    workspace_id = uuid.uuid4()
    workspace = MagicMock()
    workspace.id = workspace_id
    admin = MagicMock()
    admin.relay_role = "admin"

    call_count = 0

    def fake_get_session(workspace_id_arg=None):
        nonlocal call_count

        @asynccontextmanager
        async def _cm():
            nonlocal call_count
            session = AsyncMock()
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                # First call: workspace lookup in _authenticated_admin_workspace
                result.scalar_one_or_none.return_value = workspace
            elif call_count == 2:
                # Second call: user/admin lookup in _authenticated_admin_workspace
                result.scalar_one_or_none.return_value = admin
            else:
                # Third call: new workspace existence guard — returns None (not found)
                result.scalar_one_or_none.return_value = None
            session.execute = AsyncMock(return_value=result)
            yield session

        return _cm()

    client = TestClient(api_module.api)
    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T_TEAM", "user_id": "U_ADMIN"})),
        patch("relay.api.main.get_session", side_effect=fake_get_session),
        patch("relay.api.main.get_settings") as mock_settings,
    ):
        mock_settings.return_value.token_encryption_key_bytes = b"\xaa" * 32
        mock_settings.return_value.hubspot_client_id = "client-id"
        mock_settings.return_value.hubspot_redirect_uri = "https://relay.example.com/hubspot/oauth_redirect"

        resp = client.get(
            f"/hubspot/install?workspace_id={workspace_id}",
            headers={"Authorization": "Bearer xoxp-admin"},
        )

    assert resp.status_code == 404
