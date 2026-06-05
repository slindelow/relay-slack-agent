"""Unit tests for the shared embedding pipeline."""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.connectors.embeddings import embed_chunks


def _make_session(existing_hashes: list[str] | None = None):
    """Build a minimal mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()

    # Simulate SELECT for existing hashes
    rows = []
    if existing_hashes:
        for h in existing_hashes:
            row = MagicMock()
            row.content_hash = h
            row.id = uuid.uuid4()
            rows.append(row)

    result_mock = MagicMock()
    result_mock.__iter__ = MagicMock(return_value=iter(rows))
    session.execute = AsyncMock(return_value=result_mock)
    session.flush = AsyncMock()
    return session


FAKE_VECTOR = [0.1] * 1536


@pytest.mark.asyncio
async def test_embed_chunks_creates_rows():
    session = _make_session()
    workspace_id = uuid.uuid4()
    chunks = ["hello world", "second chunk"]

    with patch("relay.connectors.embeddings._get_embeddings", new=AsyncMock(return_value=[FAKE_VECTOR, FAKE_VECTOR])):
        ids = await embed_chunks(workspace_id, chunks, None, None, session)

    assert len(ids) == 2
    assert session.add.call_count == 2
    assert session.flush.call_count == 2


@pytest.mark.asyncio
async def test_embed_chunks_idempotent():
    """Chunks with existing content_hash must not produce new DB rows."""
    text = "already embedded"
    existing_hash = hashlib.sha256(text.encode()).hexdigest()
    session = _make_session(existing_hashes=[existing_hash])
    workspace_id = uuid.uuid4()

    with patch("relay.connectors.embeddings._get_embeddings", new=AsyncMock(return_value=[])) as mock_embed:
        ids = await embed_chunks(workspace_id, [text], None, None, session)

    assert len(ids) == 1
    mock_embed.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_embed_chunks_empty_input():
    session = _make_session()
    ids = await embed_chunks(uuid.uuid4(), [], None, None, session)
    assert ids == []
    session.execute.assert_not_called()
