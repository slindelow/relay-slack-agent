from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_handle_delete_workspace_requires_admin():
    """Deletion modal requires admin role before opening."""
    from relay.commands.delete import handle_delete_workspace

    ack = AsyncMock()
    client = AsyncMock()
    respond = AsyncMock()
    command = {"team_id": "T123", "user_id": "U_USER", "trigger_id": "trigger"}

    mock_workspace = MagicMock()
    mock_workspace.id = "workspace-123"

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
                auth_result.scalar_one_or_none.return_value = None  # non-admin
                session.execute = AsyncMock(return_value=auth_result)
            yield session
        return _cm()

    with patch("relay.db.session.get_session", side_effect=fake_get_session):
        await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    ack.assert_awaited_once()
    client.views_open.assert_not_awaited()
    respond.assert_awaited_once()
    call_kwargs = respond.await_args.kwargs
    assert "admin" in call_kwargs.get("text", "").lower()
