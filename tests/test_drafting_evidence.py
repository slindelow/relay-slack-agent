from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.connectors.retrieval import RetrievedChunk
from relay.drafting.evidence import assemble_evidence


@pytest.mark.asyncio
async def test_assemble_evidence_uses_message_excerpt_and_draft_id():
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    question = SimpleNamespace(
        id=question_id,
        title_excerpt="fallback question",
        channel_id=None,
    )
    message = SimpleNamespace(raw_excerpt="How do I configure SSO?")

    lookup_result = MagicMock()
    lookup_result.one_or_none.return_value = (question, message)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=lookup_result)

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_document_id=uuid.uuid4(),
        knowledge_entry_id=None,
        content="Enable SSO under Settings > Security.",
        embedding_model="voyage-3",
        embedding_dims=1536,
        citation={"title": "SSO docs", "provider": "google_drive", "url": "https://example.com/sso"},
    )

    with patch("relay.drafting.evidence.retrieve", new=AsyncMock(return_value=[chunk])) as mock_retrieve:
        bundle = await assemble_evidence(workspace_id, question_id, session, draft_id=draft_id)

    assert bundle.question_excerpt == "How do I configure SSO?"
    assert bundle.sources[0].title == "SSO docs"
    mock_retrieve.assert_awaited_once_with(
        workspace_id,
        "How do I configure SSO?",
        session,
        top_k=8,
        draft_id=draft_id,
    )
