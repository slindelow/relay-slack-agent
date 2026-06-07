"""Tests verifying authorization guards on destructive RELAY commands."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
