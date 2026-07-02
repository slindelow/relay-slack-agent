"""Tests for prompt-injection-safe draft generator (US-003)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.drafting.evidence import EvidenceBundle, EvidenceSource
from relay.drafting.generator import DraftOutput, _build_user_message, _ensure_usable_output


def _make_bundle(sources=None):
    return EvidenceBundle(
        question_excerpt="Why is the API returning 429?",
        account_context={"tier": "enterprise", "arr": 120000.0},
        sources=sources or [],
        total_tokens=50,
    )


def test_draft_output_requires_human_review():
    """requires_human_review must always be True — it cannot be set to False."""
    out = DraftOutput(
        summary="s",
        evidence=[],
        confidence=0.9,
        customer_draft="Hello",
        internal_brief="Brief",
        risks_or_unknowns="",
        recommended_next_action="Follow up",
    )
    assert out.requires_human_review is True


def test_build_user_message_wraps_sources_in_xml():
    src = EvidenceSource(
        title="Issue #42",
        provider="github",
        url="https://github.com/org/repo/issues/42",
        excerpt="Rate limiting is applied per API key.",
        freshness_ts=None,
        stale=False,
    )
    bundle = _make_bundle(sources=[src])
    msg = _build_user_message(bundle)

    assert "<retrieved_source" in msg
    assert 'trust="external"' in msg
    assert "Rate limiting" in msg
    assert "</retrieved_source>" in msg


def test_build_user_message_no_sources():
    bundle = _make_bundle()
    msg = _build_user_message(bundle)

    assert "<retrieved_source" not in msg
    assert "No sources retrieved" in msg


def test_build_user_message_includes_question():
    bundle = _make_bundle()
    msg = _build_user_message(bundle)

    assert "Why is the API returning 429?" in msg


def test_build_user_message_account_context():
    bundle = _make_bundle()
    msg = _build_user_message(bundle)

    assert "enterprise" in msg
    assert "120000" in msg


def test_build_user_message_includes_prepared_answer_for_repo_structure():
    src = EvidenceSource(
        title="owner/repo repository structure",
        provider="github",
        url="https://github.com/owner/repo",
        excerpt=(
            "- relay/slack/events.py\n"
            "- relay/drafting/generator.py\n"
            "- relay/connectors/github.py\n"
            "- tests/test_generator.py\n"
            "- docs/architecture.md"
        ),
        freshness_ts=None,
        stale=False,
    )
    bundle = EvidenceBundle(
        question_excerpt="Where in the repo does RELAY handle Slack event ingestion and draft generation?",
        account_context={},
        sources=[src],
        total_tokens=100,
    )

    msg = _build_user_message(bundle)

    assert "Prepared answer from retrieved sources" in msg
    assert "application code" in msg
    assert "relay/slack/events.py" in msg


@pytest.mark.asyncio
async def test_generate_draft_creates_draft_row():
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    bundle = _make_bundle()

    tool_input = {
        "summary": "Rate limiting triggered",
        "evidence": [],
        "confidence": 0.85,
        "customer_draft": "We see you're hitting rate limits.",
        "internal_brief": "Enterprise account, ARR 120k, rate limit issue.",
        "risks_or_unknowns": "Root cause unclear",
        "recommended_next_action": "Check API key quota",
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "submit_draft"
    mock_block.input = tool_input

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    session = AsyncMock()

    with (
        patch("relay.drafting.generator.AsyncAnthropic", return_value=mock_client),
        patch("relay.drafting.generator._save_draft", new_callable=AsyncMock) as mock_save,
    ):
        from relay.drafting.generator import generate_draft
        out = await generate_draft(workspace_id, question_id, bundle, session)

    assert out.confidence == 0.85
    assert out.customer_draft == "We see you're hitting rate limits."
    assert out.requires_human_review is True
    mock_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_draft_empty_sources_sets_low_confidence():
    """When sources is empty, LLM still runs but we accept low confidence."""
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    bundle = _make_bundle()

    tool_input = {
        "summary": "No sources found",
        "evidence": [],
        "confidence": 0.2,
        "customer_draft": "",
        "internal_brief": "No relevant context found.",
        "risks_or_unknowns": "Cannot draft without sources",
        "recommended_next_action": "Escalate to engineering",
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "submit_draft"
    mock_block.input = tool_input

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    session = AsyncMock()

    with (
        patch("relay.drafting.generator.AsyncAnthropic", return_value=mock_client),
        patch("relay.drafting.generator._save_draft", new_callable=AsyncMock),
    ):
        from relay.drafting.generator import generate_draft
        out = await generate_draft(workspace_id, question_id, bundle, session)

    assert out.confidence <= 0.3
    assert "confirm the details" in out.customer_draft


def test_ensure_usable_output_replaces_holding_reply_when_prepared_answer_exists():
    src = EvidenceSource(
        title="owner/repo repository structure",
        provider="github",
        url="https://github.com/owner/repo",
        excerpt=(
            "Top-level entries:\n"
            "- relay\n"
            "- tests\n"
            "- docs\n"
            "- alembic\n"
            "- scripts\n"
        ),
        freshness_ts=None,
        stale=False,
    )
    bundle = EvidenceBundle(
        question_excerpt="What is the folder structure of the RELAY repo?",
        account_context={},
        sources=[src],
        total_tokens=100,
    )
    output = DraftOutput(
        summary="Holding",
        evidence=[],
        confidence=0.2,
        customer_draft="Thanks for asking. I’ll confirm the details and follow up shortly.",
        internal_brief="Model fell back.",
        risks_or_unknowns="",
        recommended_next_action="",
    )

    out = _ensure_usable_output(bundle, output)

    assert out.confidence >= 0.7
    assert "application code" in out.customer_draft


def test_ensure_usable_output_uses_clean_multi_channel_answer():
    src = EvidenceSource(
        title="README.md",
        provider="github",
        url="https://github.com/slindelow/relay-slack-agent/blob/main/README.md",
        excerpt=(
            "RELAY monitors registered Slack Connect customer channels. "
            "/relay register #channel Company Add a channel to monitoring. "
            "/relay settings Manage connectors and team settings."
        ),
        freshness_ts=None,
        stale=False,
    )
    bundle = EvidenceBundle(
        question_excerpt="How can RELAY manage multiple channels at once? Does it need manual syncing?",
        account_context={},
        sources=[src],
        total_tokens=100,
    )
    output = DraftOutput(
        summary="Holding",
        evidence=[],
        confidence=0.2,
        customer_draft="Thanks for asking. I’ll confirm the details and follow up shortly.",
        internal_brief="Model fell back.",
        risks_or_unknowns="",
        recommended_next_action="",
    )

    out = _ensure_usable_output(bundle, output)

    assert out.confidence >= 0.7
    assert "multiple Slack Connect customer channels" in out.customer_draft
    assert "does not require manual syncing" in out.customer_draft
    assert "###" not in out.customer_draft
    assert "```" not in out.customer_draft
