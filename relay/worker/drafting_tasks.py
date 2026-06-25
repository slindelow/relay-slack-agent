"""Celery task for triggering draft generation (US-004)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="relay.generate_draft_for_question", bind=True, max_retries=0)
def generate_draft_for_question(
    self,
    workspace_id_str: str,
    question_id_str: str,
    notify_slack_user_id: str | None = None,
) -> None:
    asyncio.run(_generate_draft_async(
        uuid.UUID(workspace_id_str),
        uuid.UUID(question_id_str),
        notify_slack_user_id,
    ))


async def _generate_draft_async(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    notify_slack_user_id: str | None = None,
) -> None:
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

    # Who to notify: an explicit target (the user who claimed / clicked Generate)
    # takes precedence; otherwise fall back to the active assignment's assignee.
    csm_slack_user_id: str | None = notify_slack_user_id
    if csm_slack_user_id is None:
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

    try:
        from relay.context.mcp_server import draft_generation_tool

        # The generated draft is surfaced in the RELAY App Home "Drafts Ready for
        # Review" section (with a Review draft button) — that is the CSM's review
        # surface. We intentionally do NOT DM the CSM from here: the Bolt
        # app.client is bound to the web process's event loop and cannot post from
        # Celery's per-task asyncio.run() loop. acting_slack_user_id still scopes
        # Slack-search evidence to the CSM.
        await draft_generation_tool(
            str(workspace_id),
            str(question_id),
            acting_slack_user_id=csm_slack_user_id,
        )
    except Exception:
        logger.exception("generate_draft_for_question: error for question %s", question_id)
        raise
