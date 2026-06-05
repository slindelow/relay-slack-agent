"""Tests for prompt-injection-safe draft generator (US-003)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.drafting.evidence import EvidenceBundle, EvidenceSource
from relay.drafting.generator import DraftOutput, _build_user_message


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
    assert out.customer_draft == ""
