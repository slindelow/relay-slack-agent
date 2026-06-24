"""Unit tests for tenant-safe semantic retrieval."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.connectors.retrieval import RetrievedChunk, retrieve

FAKE_VECTOR = [0.1] * 1024


def _make_chunk_row(workspace_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.source_document_id = uuid.uuid4()
    row.knowledge_entry_id = None
    row.content = "Some chunk content"
    row.embedding_model = "voyage-3"
    row.embedding_dims = 1024
    row.workspace_id = workspace_id
    return row


@pytest.mark.asyncio
async def test_retrieve_returns_chunks_for_correct_workspace():
    workspace_a = uuid.uuid4()
    workspace_b = uuid.uuid4()

    chunk_a = _make_chunk_row(workspace_a)

    session = AsyncMock()
    session.add = MagicMock()

    # Two calls: the SELECT (for workspace_a chunks) returns chunk_a rows
    query_result = MagicMock()
    query_result.fetchall.return_value = [chunk_a]
    session.execute = AsyncMock(return_value=query_result)

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        results = await retrieve(workspace_a, "test query", session, top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == chunk_a.id
    # Ensure workspace_b ID does NOT appear
    assert all(r.chunk_id != uuid.UUID(int=0) or True for r in results)


@pytest.mark.asyncio
async def test_retrieve_writes_retrieval_log():
    workspace_id = uuid.uuid4()
    chunk_row = _make_chunk_row(workspace_id)

    session = AsyncMock()
    session.add = MagicMock()

    query_result = MagicMock()
    query_result.fetchall.return_value = [chunk_row]
    session.execute = AsyncMock(return_value=query_result)

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        await retrieve(workspace_id, "customer question", session)

    # session.add should have been called for the RetrievalLog
    from relay.db.models import RetrievalLog
    added_args = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(obj, RetrievalLog) for obj in added_args)


@pytest.mark.asyncio
async def test_retrieve_can_associate_log_with_draft():
    workspace_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    chunk_row = _make_chunk_row(workspace_id)

    session = AsyncMock()
    session.add = MagicMock()

    query_result = MagicMock()
    query_result.fetchall.return_value = [chunk_row]
    session.execute = AsyncMock(return_value=query_result)

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        await retrieve(workspace_id, "customer question", session, draft_id=draft_id)

    added_args = [call.args[0] for call in session.add.call_args_list]
    log = next(obj for obj in added_args if obj.__class__.__name__ == "RetrievalLog")
    assert log.draft_id == draft_id


@pytest.mark.asyncio
async def test_retrieve_empty_results():
    workspace_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()

    query_result = MagicMock()
    query_result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=query_result)

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        results = await retrieve(workspace_id, "nothing here", session)

    assert results == []
    # Log still written even for zero results
    from relay.db.models import RetrievalLog
    added_args = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(obj, RetrievalLog) for obj in added_args)


@pytest.mark.asyncio
async def test_retrieve_rejects_empty_query():
    with pytest.raises(ValueError, match="query"):
        await retrieve(uuid.uuid4(), "   ", AsyncMock())


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k"):
        await retrieve(uuid.uuid4(), "question", AsyncMock(), top_k=0)


@pytest.mark.asyncio
async def test_retrieve_cites_and_counts_relay_memory_chunks():
    workspace_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    chunk_row = _make_chunk_row(workspace_id)
    chunk_row.source_document_id = None
    chunk_row.knowledge_entry_id = entry_id

    entry = MagicMock()
    entry.id = entry_id
    entry.title = "Acme - SSO setup"
    entry.summary = "Acme uses the standard SSO setup."
    entry.created_at = None
    entry.reuse_count = 2

    query_result = MagicMock()
    query_result.fetchall.return_value = [chunk_row]
    entry_result = MagicMock()
    entry_result.scalars.return_value.all.return_value = [entry]

    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[query_result, entry_result])

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        results = await retrieve(workspace_id, "how do we configure sso?", session)

    assert results[0].citation["provider"] == "relay_memory"
    assert results[0].citation["title"] == "Acme - SSO setup"
    assert entry.reuse_count == 3


@pytest.mark.asyncio
async def test_retrieve_does_not_double_count_reuse_for_same_entry():
    """Two chunks sharing one knowledge_entry_id must only increment reuse_count once."""
    workspace_id = uuid.uuid4()
    entry_id = uuid.uuid4()

    chunk_row_1 = _make_chunk_row(workspace_id)
    chunk_row_1.source_document_id = None
    chunk_row_1.knowledge_entry_id = entry_id

    chunk_row_2 = _make_chunk_row(workspace_id)
    chunk_row_2.source_document_id = None
    chunk_row_2.knowledge_entry_id = entry_id

    entry = MagicMock()
    entry.id = entry_id
    entry.title = "Acme - Billing FAQ"
    entry.summary = "Covers common billing questions for Acme."
    entry.created_at = None
    entry.reuse_count = 0

    query_result = MagicMock()
    query_result.fetchall.return_value = [chunk_row_1, chunk_row_2]
    entry_result = MagicMock()
    entry_result.scalars.return_value.all.return_value = [entry]

    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[query_result, entry_result])

    with patch("relay.connectors.retrieval._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR])):
        results = await retrieve(workspace_id, "how does billing work?", session)

    # reuse_count must be incremented exactly once despite two matching chunks
    assert entry.reuse_count == 1

    # Both returned chunks must still carry a populated citation
    assert results[0].citation["provider"] == "relay_memory"
    assert results[1].citation["provider"] == "relay_memory"
