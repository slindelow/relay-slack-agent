from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.worker.deletion_tasks import _DELETE_ORDER, create_workspace_deletion_job


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_delete_order_removes_chunks_before_sources_and_workspace_last():
    names = [model.__tablename__ for model in _DELETE_ORDER]
    assert names.index("knowledge_chunks") < names.index("source_documents")
    assert names.index("source_documents") < names.index("source_connectors")
    assert names.index("questions") < names.index("messages")
    assert "workspaces" not in names


@pytest.mark.asyncio
async def test_create_workspace_deletion_job_records_pending_job():
    workspace_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("relay.worker.deletion_tasks.get_session", return_value=_SessionContext(session)):
        job = await create_workspace_deletion_job(workspace_id, actor_slack_user_id="U123")

    assert job.workspace_id == workspace_id
    assert job.status == "pending"
    assert job.actor_slack_user_id == "U123"
    session.add.assert_called_once_with(job)
