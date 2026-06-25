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

        await draft_generation_tool(
            str(workspace_id),
            str(question_id),
            acting_slack_user_id=csm_slack_user_id,
        )

        if csm_slack_user_id:
            draft_id, excerpt = await _latest_pending_draft(workspace_id, question_id)
            if draft_id is not None:
                await _notify_draft_ready(csm_slack_user_id, draft_id, excerpt)
            else:
                await _notify_csm(csm_slack_user_id, "Draft ready — open the RELAY App Home to review it.")

    except Exception:
        logger.exception("generate_draft_for_question: error for question %s", question_id)
        if csm_slack_user_id:
            await _notify_csm(csm_slack_user_id, ":x: Draft generation failed. Please try again or contact support.")
        raise


async def _latest_pending_draft(
    workspace_id: uuid.UUID, question_id: uuid.UUID
) -> tuple[uuid.UUID | None, str]:
    """Return (draft_id, question_excerpt) for the newest pending draft, or (None, '')."""
    from sqlalchemy import select

    from relay.db.models import Draft, Question
    from relay.db.session import get_session

    async with get_session(workspace_id) as session:
        result = await session.execute(
            select(Draft.id, Question.title_excerpt)
            .join(Question, Draft.question_id == Question.id)
            .where(
                Draft.workspace_id == workspace_id,
                Draft.question_id == question_id,
                Draft.status == "pending",
            )
            .order_by(Draft.created_at.desc())
        )
        row = result.first()
    if row is not None:
        return row[0], (row[1] or "")
    return None, ""


async def _notify_draft_ready(slack_user_id: str, draft_id: uuid.UUID, excerpt: str) -> None:
    """DM the CSM a draft-ready card with a working Review draft button."""
    try:
        from relay.slack.app import app

        clean = (excerpt or "").strip()[:140]
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":memo: *Draft ready for review*\n_{clean}…_" if clean else ":memo: *Draft ready for review*",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review draft"},
                        "style": "primary",
                        "action_id": "relay_open_draft_modal",
                        "value": str(draft_id),
                    }
                ],
            },
        ]
        await app.client.chat_postMessage(
            channel=slack_user_id,
            text="Draft ready — click Review draft to approve.",
            blocks=blocks,
        )
    except Exception:
        logger.warning("generate_draft_for_question: failed to notify CSM %s", slack_user_id)


async def _notify_csm(slack_user_id: str, text: str) -> None:
    try:
        from relay.slack.app import app
        await app.client.chat_postMessage(channel=slack_user_id, text=text)
    except Exception:
        logger.warning("generate_draft_for_question: failed to notify CSM %s", slack_user_id)
