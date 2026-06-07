from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.drafting.memory import index_approved_response


@pytest.mark.asyncio
async def test_index_approved_response_creates_memory_and_embedding():
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    question = SimpleNamespace(
        id=question_id,
        title_excerpt="How do we configure SSO?",
        account_id=uuid.uuid4(),
    )
    account = SimpleNamespace(name="Acme")
    draft = SimpleNamespace(
        id=draft_id,
        question_id=question_id,
        customer_draft="Enable SAML SSO from Settings > Security.",
        internal_brief="Use the enterprise setup path.",
        evidence_bundle={"sources": [{"title": "SSO docs"}]},
    )

    question_result = MagicMock()
    question_result.one_or_none.return_value = (question, account)
    draft_result = MagicMock()
    draft_result.scalar_one_or_none.return_value = draft

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=[question_result, draft_result])

    with (
        patch("relay.drafting.memory._summarize_resolution", new=AsyncMock(return_value="Acme SSO setup uses SAML.")),
        patch("relay.drafting.memory.embed_chunks", new=AsyncMock(return_value=[uuid.uuid4()])) as mock_embed,
    ):
        entry = await index_approved_response(workspace_id, question_id, draft_id, session)

    assert entry.workspace_id == workspace_id
    assert entry.question_id == question_id
    assert entry.customer_question == "How do we configure SSO?"
    assert entry.internal_answer == "Enable SAML SSO from Settings > Security."
    assert entry.summary == "Acme SSO setup uses SAML."
    assert entry.title.startswith("Acme — How do we configure SSO?")
    mock_embed.assert_awaited_once()
    assert mock_embed.await_args.kwargs["knowledge_entry_id"] == entry.id
