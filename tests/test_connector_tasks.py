"""Unit tests for connector Celery task helpers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.worker.connector_tasks import _sync_all_connectors_async, _sync_connector_async


def _make_connector_row(connector_id, workspace_id, connector_type="google_drive"):
    row = MagicMock()
    row.id = connector_id
    row.workspace_id = workspace_id
    row.connector_type = connector_type
    row.sync_status = "not_synced"
    row.last_synced_at = None
    row.disconnected_at = None
    return row


def _session_context(session):
    @asynccontextmanager
    async def _ctx(workspace_id=None):
        yield session

    return _ctx


@pytest.mark.asyncio
async def test_sync_connector_updates_last_synced_at():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row = _make_connector_row(connector_id, workspace_id)

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = connector_row
    session.execute = AsyncMock(return_value=result)

    mock_connector = AsyncMock()
    mock_connector.sync = AsyncMock()

    with (
        patch("relay.worker.connector_tasks.get_session", new=_session_context(session)),
        patch("relay.worker.connector_tasks.registry.get_connector", return_value=mock_connector),
    ):
        await _sync_connector_async(workspace_id, connector_id)

    assert connector_row.sync_status == "synced"
    assert connector_row.last_synced_at is not None
    mock_connector.sync.assert_awaited_once_with(workspace_id)


@pytest.mark.asyncio
async def test_sync_connector_sets_error_on_exception():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    connector_row = _make_connector_row(connector_id, workspace_id)

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = connector_row
    session.execute = AsyncMock(return_value=result)

    mock_connector = AsyncMock()
    mock_connector.sync = AsyncMock(side_effect=RuntimeError("API error"))

    with (
        patch("relay.worker.connector_tasks.get_session", new=_session_context(session)),
        patch("relay.worker.connector_tasks.registry.get_connector", return_value=mock_connector),
    ):
        await _sync_connector_async(workspace_id, connector_id)

    assert connector_row.sync_status == "error"


@pytest.mark.asyncio
async def test_sync_all_connectors_enqueues_per_connector():
    workspace_id = uuid.uuid4()
    connector_id = uuid.uuid4()

    row = MagicMock()
    row.workspace_id = workspace_id
    row.id = connector_id

    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    with (
        patch("relay.worker.connector_tasks.get_session", new=_session_context(session)),
        patch("relay.worker.connector_tasks.sync_connector.delay") as mock_delay,
    ):
        await _sync_all_connectors_async()

    mock_delay.assert_called_once_with(str(workspace_id), str(connector_id))
