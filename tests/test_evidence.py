"""Tests for the evidence bundle constructor (US-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.drafting.evidence import (
    EvidenceBundle,
    EvidenceSource,
    _count_tokens,
    _is_stale,
    _source_priority,
    assemble_evidence,
)


def test_source_priority_order():
    assert _source_priority("crm") < _source_priority("github")
    assert _source_priority("github") < _source_priority("google_drive")
    assert _source_priority("google_drive") < _source_priority("knowledge_entry")
    assert _source_priority("unknown") > _source_priority("knowledge_entry")


def test_is_stale_none():
    assert _is_stale(None) is True


def test_is_stale_recent():
    assert _is_stale(datetime.now(UTC) - timedelta(hours=1)) is False


def test_is_stale_old():
    assert _is_stale(datetime.now(UTC) - timedelta(hours=49)) is True


def test_count_tokens_nonempty():
    count = _count_tokens("hello world")
    assert count > 0


def test_count_tokens_empty():
    assert _count_tokens("") == 0


def _make_session_with_question(question_text: str = "Why does my API return 500?", channel_id=None):
    """Build an AsyncMock session that returns a (Question, Message) row."""
    mock_question = MagicMock()
    mock_question.channel_id = channel_id
    mock_question.title_excerpt = question_text

    mock_message = MagicMock()
    mock_message.raw_excerpt = question_text

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = (mock_question, mock_message)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=lookup_result)
    return session


@pytest.mark.asyncio
async def test_assemble_evidence_no_question():
    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=lookup_result)

    with pytest.raises(ValueError, match="not found"):
        await assemble_evidence(uuid.uuid4(), uuid.uuid4(), session)


@pytest.mark.asyncio
async def test_assemble_evidence_empty_sources():
    """When retrieve() returns nothing, sources list is empty."""
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    session = _make_session_with_question()

    with patch("relay.drafting.evidence.retrieve", new_callable=AsyncMock, return_value=[]):
        bundle = await assemble_evidence(workspace_id, question_id, session)

    assert "Why does my API return 500?" in bundle.question_excerpt
    assert bundle.sources == []
    assert bundle.total_tokens > 0


@pytest.mark.asyncio
async def test_assemble_evidence_deduplicates():
    """Same URL from two retrieve() calls should appear once."""
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    session = _make_session_with_question("Test question")

    chunk = MagicMock()
    chunk.content = "Some content"
    chunk.citation = {"title": "Issue #1", "url": "https://github.com/org/repo/issues/1", "updated_at": None, "stale": False}

    with patch("relay.drafting.evidence.retrieve", new_callable=AsyncMock, return_value=[chunk, chunk]):
        bundle = await assemble_evidence(workspace_id, question_id, session)

    urls = [s.url for s in bundle.sources]
    assert len(urls) == len(set(u for u in urls if u))


@pytest.mark.asyncio
async def test_assemble_evidence_token_budget():
    """Sources exceeding token budget are dropped."""
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    session = _make_session_with_question("short")

    big_chunks = []
    for i in range(20):
        c = MagicMock()
        c.content = "word " * 1000
        c.citation = {"title": f"Doc {i}", "url": f"https://example.com/{i}", "updated_at": None, "stale": False}
        big_chunks.append(c)

    with patch("relay.drafting.evidence.retrieve", new_callable=AsyncMock, return_value=big_chunks):
        bundle = await assemble_evidence(workspace_id, question_id, session)

    assert bundle.total_tokens <= 8000
