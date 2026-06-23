"""Compatibility facade for governed evidence assembly."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from relay.context.contracts import ContextSource as EvidenceSource
from relay.context.contracts import EvidenceBundle
from relay.context.service import assemble_evidence_for_question


async def assemble_evidence(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    session: AsyncSession,
    draft_id: uuid.UUID | None = None,
    acting_slack_user_id: str | None = None,
) -> EvidenceBundle:
    """Gather all relevant context for a question through the context tool boundary."""
    return await assemble_evidence_for_question(
        workspace_id,
        question_id,
        session,
        draft_id=draft_id,
        acting_slack_user_id=acting_slack_user_id,
    )
