from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.commands.ask import (
    _dedupe_and_rank_sources,
    _escape_mrkdwn,
    _format_result_blocks,
    _parse_ask_query,
    handle_ask,
)
from relay.context.contracts import ContextSource
from relay.context.slack_rts import SlackSearchStatus


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


def test_format_result_blocks_returns_answer_without_raw_source_metadata():
    chunk = ContextSource(
        title="SSO docs",
        provider="google_drive",
        url="https://example.com",
        excerpt="Enable SSO under Settings > Security.",
        stale=False,
    )

    blocks = _format_result_blocks("How do I configure SSO?", [chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "*Answer*" in text
    assert "*Citations*" in text
    assert "SSO docs" in text
    assert "Enable SSO" in text
    assert "`google_drive`" not in text
    assert "`customer-safe`" not in text
    assert "_fresh_" not in text


def test_escape_mrkdwn():
    assert _escape_mrkdwn("a & b") == "a &amp; b"
    assert _escape_mrkdwn("<b>") == "&lt;b&gt;"
    assert _escape_mrkdwn("no special chars") == "no special chars"


def test_format_result_blocks_escapes_title_and_excerpt():
    chunk = ContextSource(
        title="Docs & Guide",
        provider="confluence",
        url="https://example.com",
        excerpt="Use <b>bold</b> & proper markup.",
        stale=False,
    )

    blocks = _format_result_blocks("Docs guide", [chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "Docs &amp; Guide" in text
    assert "&lt;b&gt;" in text
    # Raw unescaped chars must not appear inside mrkdwn
    assert "*Docs & Guide*" not in text


def test_format_result_blocks_non_https_url_falls_back_to_text():
    chunk = ContextSource(
        title="Risky Doc",
        provider="confluence",
        url="javascript:alert(1)",
        excerpt="Some content.",
        stale=False,
    )

    blocks = _format_result_blocks("Risky Doc", [chunk])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    # URL must not be embedded; title should still appear as plain text
    assert "javascript:" not in text
    assert "Risky Doc" in text


def test_repo_structure_query_prefers_github_structure_source():
    memory = ContextSource(
        title="TestCo - current status",
        provider="relay_memory",
        url=None,
        excerpt="RELAY status update from a prior customer conversation.",
        stale=False,
    )
    structure = ContextSource(
        title="owner/repo repository structure",
        provider="github",
        url="https://github.com/owner/repo",
        excerpt=(
            "REPOSITORY STRUCTURE for owner/repo\n\n"
            "Top-level entries:\n"
            "- relay\n"
            "- tests\n"
            "- docs\n"
            "- alembic\n"
            "- scripts\n\n"
            "All directories:\n"
            "- relay/\n"
            "- relay/commands/\n"
            "- relay/connectors/\n"
            "- tests/\n"
            "- docs/"
        ),
        stale=False,
    )

    ranked = _dedupe_and_rank_sources(
        "what is the folder structure of the RELAY repo?",
        [memory, structure],
    )
    blocks = _format_result_blocks(
        "what is the folder structure of the RELAY repo?",
        [memory, structure],
    )
    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)

    assert ranked[0] == structure
    assert "`relay/`" in text
    assert "`tests/`" in text
    assert "`docs/`" in text
    assert "TestCo" not in text.split("*Citations*")[0]


def test_dedupe_and_rank_sources_filters_weak_unrelated_results():
    unrelated = ContextSource(
        title="Billing policy",
        provider="relay_memory",
        url=None,
        excerpt="Refund windows and billing escalation contacts.",
        stale=False,
    )

    assert _dedupe_and_rank_sources("what is the folder structure of the RELAY repo?", [unrelated]) == []


def test_where_does_handle_query_uses_repo_structure_intent_ranking():
    structure = ContextSource(
        title="owner/repo repository structure",
        provider="github",
        url="https://github.com/owner/repo",
        excerpt=(
            "REPOSITORY STRUCTURE for owner/repo\n\n"
            "Top-level entries:\n"
            "- relay\n"
            "- tests\n\n"
            "All directories:\n"
            "- relay/slack/\n"
            "- relay/drafting/\n"
            "- relay/connectors/"
        ),
        stale=False,
    )
    weak_memory = ContextSource(
        title="Where in repo customer question",
        provider="relay_memory",
        url=None,
        excerpt="A prior customer asked where a billing setting lives.",
        stale=False,
    )

    ranked = _dedupe_and_rank_sources(
        "where does the repo handle Slack event ingestion and GitHub knowledge retrieval?",
        [weak_memory, structure],
    )

    assert ranked[0] == structure


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
        patch("relay.commands.ask.slack_search_status", new=AsyncMock(return_value=SlackSearchStatus(False))),
        patch("relay.commands.ask.search_indexed_knowledge", new=AsyncMock(return_value=[])),
        patch("relay.commands.ask.search_slack_context", new=AsyncMock(return_value=[])),
    ):
        await handle_ask(ack, respond, {"text": "ask SSO docs", "team_id": "T123", "user_id": "U123"})

    respond.assert_awaited_once_with(
        response_type="ephemeral",
        text="No relevant sources found in connected knowledge base. Connect Slack Search in `/relay settings` to include internal Slack context.",
    )


@pytest.mark.asyncio
async def test_handle_ask_returns_formatted_blocks():
    workspace_id = uuid.uuid4()
    unscoped_session = AsyncMock()
    workspace_result = MagicMock()
    workspace_result.scalar_one_or_none.return_value = SimpleNamespace(id=workspace_id)
    unscoped_session.execute.return_value = workspace_result
    scoped_session = AsyncMock()
    chunk = ContextSource(
        title="Acme - SSO",
        provider="relay_memory",
        url=None,
        excerpt="Use the approved Acme SSO answer.",
        stale=False,
    )

    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch(
            "relay.commands.ask.get_session",
            side_effect=[_SessionContext(unscoped_session), _SessionContext(scoped_session)],
        ),
        patch("relay.commands.ask.slack_search_status", new=AsyncMock(return_value=SlackSearchStatus(True))),
        patch("relay.commands.ask.search_indexed_knowledge", new=AsyncMock(return_value=[chunk])) as mock_search,
        patch("relay.commands.ask.search_slack_context", new=AsyncMock(return_value=[])),
    ):
        await handle_ask(ack, respond, {"text": "ask SSO docs", "team_id": "T123", "user_id": "U123"})

    mock_search.assert_awaited_once_with(
        workspace_id,
        "SSO docs",
        scoped_session,
        top_k=5,
        actor_slack_user_id="U123",
    )
    kwargs = respond.await_args.kwargs
    assert kwargs["response_type"] == "ephemeral"
    assert "blocks" in kwargs
