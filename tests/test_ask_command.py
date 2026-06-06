from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.commands.ask import _escape_mrkdwn, _format_result_blocks, _parse_ask_query, handle_ask
from relay.connectors.retrieval import RetrievedChunk


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_parse_ask_query_strips_subcommand():
    assert _parse_ask_query("ask how do I configure SSO?") == "how do I configure SSO?"
    assert _parse_ask_query("how do I configure SSO?") == "how do I configure SSO?"


def test_parse_ask_query_word_boundary():
    # "asking" must NOT be stripped — only bare "ask " prefix
    assert _parse_ask_query("asking about SSO") == "asking about SSO"


def test_format_result_blocks_includes_source_metadata():
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_document_id=uuid.uuid4(),
        knowledge_entry_id=None,
        content="Enable SSO under Settings > Security.",
        embedding_model="voyage-3",
        embedding_dims=1536,
        citation={"title": "SSO docs", "provider": "google_drive", "url": "https://example.com", "stale": False},
    )

    blocks = _format_result_blocks([chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "SSO docs" in text
    assert "google_drive" in text
    assert "Enable SSO" in text


def test_escape_mrkdwn():
    assert _escape_mrkdwn("a & b") == "a &amp; b"
    assert _escape_mrkdwn("<b>") == "&lt;b&gt;"
    assert _escape_mrkdwn("no special chars") == "no special chars"


def test_format_result_blocks_escapes_title_and_excerpt():
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_document_id=uuid.uuid4(),
        knowledge_entry_id=None,
        content="Use <b>bold</b> & proper markup.",
        embedding_model="voyage-3",
        embedding_dims=1536,
        citation={"title": "Docs & Guide", "provider": "confluence", "url": "https://example.com", "stale": False},
    )

    blocks = _format_result_blocks([chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "Docs &amp; Guide" in text
    assert "&lt;b&gt;" in text
    # Raw unescaped chars must not appear inside mrkdwn
    assert "*Docs & Guide*" not in text


def test_format_result_blocks_non_https_url_falls_back_to_text():
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_document_id=uuid.uuid4(),
        knowledge_entry_id=None,
        content="Some content.",
        embedding_model="voyage-3",
        embedding_dims=1536,
        citation={"title": "Risky Doc", "provider": "confluence", "url": "javascript:alert(1)", "stale": False},
    )

    blocks = _format_result_blocks([chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    # URL must not be embedded; title should still appear as plain text
    assert "javascript:" not in text
    assert "Risky Doc" in text


@pytest.mark.asyncio
async def test_handle_ask_empty_query_returns_usage():
    ack = AsyncMock()
    respond = AsyncMock()

    # Bare "ask" with no arguments should yield empty query
    await handle_ask(ack, respond, {"text": "ask", "team_id": "T123"})

    ack.assert_awaited_once()
    respond.assert_awaited_once_with(response_type="ephemeral", text="Usage: /relay ask <your question>")


@pytest.mark.asyncio
async def test_handle_ask_zero_results():
    workspace_id = uuid.uuid4()
    unscoped_session = AsyncMock()
    workspace_result = MagicMock()
    workspace_result.scalar_one_or_none.return_value = SimpleNamespace(id=workspace_id)
    unscoped_session.execute.return_value = workspace_result
    scoped_session = AsyncMock()

    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch(
            "relay.commands.ask.get_session",
            side_effect=[_SessionContext(unscoped_session), _SessionContext(scoped_session)],
        ),
        patch("relay.commands.ask.retrieve", new=AsyncMock(return_value=[])),
    ):
        await handle_ask(ack, respond, {"text": "ask SSO docs", "team_id": "T123"})

    respond.assert_awaited_once_with(
        response_type="ephemeral",
        text="No relevant sources found in connected knowledge base.",
    )


@pytest.mark.asyncio
async def test_handle_ask_returns_formatted_blocks():
    workspace_id = uuid.uuid4()
    unscoped_session = AsyncMock()
    workspace_result = MagicMock()
    workspace_result.scalar_one_or_none.return_value = SimpleNamespace(id=workspace_id)
    unscoped_session.execute.return_value = workspace_result
    scoped_session = AsyncMock()
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_document_id=None,
        knowledge_entry_id=uuid.uuid4(),
        content="Use the approved Acme SSO answer.",
        embedding_model="voyage-3",
        embedding_dims=1536,
        citation={"title": "Acme - SSO", "provider": "relay_memory", "stale": False},
    )

    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch(
            "relay.commands.ask.get_session",
            side_effect=[_SessionContext(unscoped_session), _SessionContext(scoped_session)],
        ),
        patch("relay.commands.ask.retrieve", new=AsyncMock(return_value=[chunk])) as mock_retrieve,
    ):
        await handle_ask(ack, respond, {"text": "ask SSO docs", "team_id": "T123"})

    mock_retrieve.assert_awaited_once_with(workspace_id, "SSO docs", scoped_session, top_k=5)
    kwargs = respond.await_args.kwargs
    assert kwargs["response_type"] == "ephemeral"
    assert "blocks" in kwargs
