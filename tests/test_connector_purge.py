"""Tests for connector-level purge (Plan 7 US-003)."""

from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest


@pytest.mark.asyncio
async def test_disconnect_connector_purges_chunks_and_marks_disconnected():
    from relay.slack.settings import relay_disconnect_connector

    connector_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_connector = MagicMock()
    mock_connector.id = connector_id
    mock_connector.connector_type = "google_drive"

    mock_doc_row = (doc_id,)

    ack = AsyncMock()
    respond = AsyncMock()
    body = {
        "actions": [{"value": str(connector_id)}],
        "team": {"id": "T123"},
    }

    mock_workspace = MagicMock()
    mock_workspace.id = workspace_id

    unscoped_session = AsyncMock()
    unscoped_session.__aenter__ = AsyncMock(return_value=unscoped_session)
    unscoped_session.__aexit__ = AsyncMock(return_value=False)
    unscoped_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_workspace))
    )

    scoped_session = AsyncMock()
    scoped_session.__aenter__ = AsyncMock(return_value=scoped_session)
    scoped_session.__aexit__ = AsyncMock(return_value=False)
    scoped_session.commit = AsyncMock()

    execute_calls = [
        # Load connector
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_connector)),
        # Get doc ids
        MagicMock(fetchall=MagicMock(return_value=[mock_doc_row])),
        # Delete chunks
        MagicMock(),
        # Delete documents
        MagicMock(),
        # Update connector
        MagicMock(),
    ]
    scoped_session.execute = AsyncMock(side_effect=execute_calls)

    def fake_get_session(workspace_id=None):
        return unscoped_session if workspace_id is None else scoped_session

    with patch("relay.db.session.get_session", side_effect=fake_get_session):
        await relay_disconnect_connector(ack=ack, body=body, respond=respond)

    ack.assert_called_once()
    respond.assert_called_once()
    resp_kwargs = respond.call_args.kwargs
    assert "disconnected" in resp_kwargs.get("text", "").lower()
    assert scoped_session.commit.called
