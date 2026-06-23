from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from relay.context.contracts import EvidenceBundle
from relay.drafting.evidence import assemble_evidence


@pytest.mark.asyncio
async def test_assemble_evidence_uses_message_excerpt_and_draft_id():
    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    session = AsyncMock()
    expected = EvidenceBundle(question_excerpt="How do I configure SSO?", account_context={})

    with patch(
        "relay.drafting.evidence.assemble_evidence_for_question",
        new=AsyncMock(return_value=expected),
    ) as mocked:
        bundle = await assemble_evidence(workspace_id, question_id, session, draft_id=draft_id)

    assert bundle is expected
    mocked.assert_awaited_once_with(
        workspace_id,
        question_id,
        session,
        draft_id=draft_id,
        acting_slack_user_id=None,
    )
