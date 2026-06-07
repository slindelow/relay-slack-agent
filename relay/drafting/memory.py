"""Resolution memory indexing for approved RELAY responses."""

from __future__ import annotations

import logging
import uuid

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.connectors.embeddings import embed_chunks
from relay.db.models import CustomerAccount, Draft, KnowledgeEntry, Question

logger = logging.getLogger(__name__)

_SUMMARY_MODEL = "claude-haiku-4-5-20251001"


async def index_approved_response(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    draft_id: uuid.UUID,
    session: AsyncSession,
) -> KnowledgeEntry:
    """Persist a sent draft as reusable resolution memory and embed it."""
    q_result = await session.execute(
        select(Question, CustomerAccount)
        .outerjoin(
            CustomerAccount,
            (CustomerAccount.workspace_id == Question.workspace_id)
            & (CustomerAccount.id == Question.account_id),
        )
        .where(
            Question.workspace_id == workspace_id,
            Question.id == question_id,
        )
    )
    row = q_result.one_or_none()
    if row is None:
        raise ValueError(f"Question {question_id} not found")
    question, account = row

    draft_result = await session.execute(
        select(Draft).where(
            Draft.workspace_id == workspace_id,
            Draft.id == draft_id,
            Draft.question_id == question_id,
        )
    )
    draft = draft_result.scalar_one_or_none()
    if draft is None:
        raise ValueError(f"Draft {draft_id} not found")

    customer_question = question.title_excerpt
    internal_answer = draft.customer_draft or ""
    summary = await _summarize_resolution(customer_question, internal_answer)

    account_name = account.name if account is not None else "Customer"
    entry = KnowledgeEntry(
        workspace_id=workspace_id,
        question_id=question_id,
        title=f"{account_name} — {customer_question[:80]}",
        summary=summary,
        customer_question=customer_question,
        internal_answer=internal_answer,
        source_bundle=draft.evidence_bundle or {},
    )
    session.add(entry)
    await session.flush()

    text = f"{customer_question}\n\n{internal_answer}".strip()
    if text:
        await embed_chunks(
            workspace_id,
            [text],
            connector_id=None,
            source_document_id=None,
            session=session,
            knowledge_entry_id=entry.id,
        )

    return entry


async def _summarize_resolution(customer_question: str, internal_answer: str) -> str:
    """Generate a one-sentence memory summary with a defensive local fallback."""
    prompt = (
        "Summarize in one sentence:\n\n"
        f"Customer question: {customer_question}\n\n"
        f"Approved answer: {internal_answer}"
    )
    try:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=_SUMMARY_MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [getattr(block, "text", "") for block in response.content]
        summary = " ".join(part.strip() for part in parts if part.strip()).strip()
    except Exception:
        logger.warning("_summarize_resolution: Haiku call failed, using fallback", exc_info=True)
        summary = ""

    if summary:
        return summary
    fallback = internal_answer.strip().splitlines()[0] if internal_answer.strip() else customer_question
    return fallback[:240]
