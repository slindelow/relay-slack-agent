"""Celery task for triggering draft generation (US-004)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="relay.generate_draft_for_question", bind=True, max_retries=0)
def generate_draft_for_question(self, workspace_id_str: str, question_id_str: str) -> None:
    asyncio.run(_generate_draft_async(
        uuid.UUID(workspace_id_str),
        uuid.UUID(question_id_str),
    ))


async def _generate_draft_async(workspace_id: uuid.UUID, question_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from relay.db.models import Assignment, Question, QuestionState
    from relay.db.session import get_session
    from relay.drafting.evidence import assemble_evidence
    from relay.drafting.generator import generate_draft

    # Check question is in claimed state
    async with get_session() as unscoped:
        q_result = await unscoped.execute(
            select(Question).where(Question.id == question_id)
        )
        question = q_result.scalar_one_or_none()

    if question is None:
        logger.warning("generate_draft_for_question: question %s not found", question_id)
        return

    if question.state != QuestionState.claimed.value:
        logger.warning(
            "generate_draft_for_question: question %s is in state %s, expected claimed — skipping",
            question_id,
            question.state,
        )
        return

    # Find CSM's Slack user ID from active assignment
    csm_slack_user_id: str | None = None
    async with get_session(workspace_id) as session:
        assign_result = await session.execute(
            select(Assignment).where(
                Assignment.workspace_id == workspace_id,
                Assignment.question_id == question_id,
                Assignment.unassigned_at.is_(None),
            )
        )
        assignment = assign_result.scalar_one_or_none()
        if assignment:
            from relay.db.models import User
            user_result = await session.execute(
                select(User).where(
                    User.workspace_id == workspace_id,
                    User.id == assignment.assignee_user_id,
                )
            )
            user = user_result.scalar_one_or_none()
            if user:
                csm_slack_user_id = user.slack_user_id

    # Generate draft
    try:
        async with get_session(workspace_id) as session:
            bundle = await assemble_evidence(
                workspace_id,
                question_id,
                session,
                acting_slack_user_id=csm_slack_user_id,
            )
            await generate_draft(workspace_id, question_id, bundle, session)

        if csm_slack_user_id:
            await _notify_csm(csm_slack_user_id, "Draft ready — click *Review draft* to approve.")

    except Exception:
        logger.exception("generate_draft_for_question: error for question %s", question_id)
        if csm_slack_user_id:
            await _notify_csm(csm_slack_user_id, ":x: Draft generation failed. Please try again or contact support.")
        raise


async def _notify_csm(slack_user_id: str, text: str) -> None:
    try:
        from relay.slack.app import app
        await app.client.chat_postMessage(channel=slack_user_id, text=text)
    except Exception:
        logger.warning("generate_draft_for_question: failed to notify CSM %s", slack_user_id)
