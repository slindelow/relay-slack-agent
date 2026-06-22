"""Tests for the evidence bundle constructor (US-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from relay.context.contracts import EvidenceBundle
from relay.context.service import _count_tokens, _is_stale, _source_priority
from relay.drafting.evidence import assemble_evidence


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

@pytest.mark.asyncio
async def test_assemble_evidence_delegates_to_context_service():
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    session = AsyncMock()
    expected = EvidenceBundle(question_excerpt="Why does my API return 500?", account_context={})

    with patch(
        "relay.drafting.evidence.assemble_evidence_for_question",
        new=AsyncMock(return_value=expected),
    ) as mocked:
        bundle = await assemble_evidence(
            workspace_id,
            question_id,
            session,
            acting_slack_user_id="U_CSM",
        )

    assert bundle is expected
    mocked.assert_awaited_once_with(
        workspace_id,
        question_id,
        session,
        draft_id=None,
        acting_slack_user_id="U_CSM",
    )
