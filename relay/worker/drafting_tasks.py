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

    from relay.db.models import Assignment, Question, QuestionState, Workspace
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

    # Build a standalone AsyncWebClient once, up front. NOTE: this must be a
    # fresh client constructed with a plain bot token (mirrors relay/sla/poller.py),
    # NOT `relay.slack.app.app.client` — that singleton is bound to the web
    # process's event loop and was already tried + reverted here once before
    # (commit 7cf92c6) because it raised "Event loop is closed" inside Celery's
    # per-task asyncio.run() loop. A freshly constructed AsyncWebClient has no
    # such binding and is safe to use from a worker task.
    # Used both to push a "ready" notification on success and a failure
    # notification if generation blows up, so the CSM is never left waiting
    # indefinitely with no explanation either way.
    slack_client = None
    workspace = None
    if csm_slack_user_id:
        try:
            from slack_sdk.web.async_client import AsyncWebClient

            from relay.slack.oauth import get_bot_token

            async with get_session(workspace_id) as session:
                ws_result = await session.execute(
                    select(Workspace).where(Workspace.id == workspace_id)
                )
                workspace = ws_result.scalar_one_or_none()
                bot_token = await get_bot_token(session, workspace_id)
            if workspace and bot_token:
                slack_client = AsyncWebClient(token=bot_token)
        except Exception:
            logger.warning(
                "generate_draft_for_question: could not build Slack client for question %s",
                question_id,
                exc_info=True,
            )

    try:
        from relay.context.mcp_server import draft_generation_tool

        # The generated draft is surfaced in the RELAY App Home "Drafts Ready for
        # Review" section (with a Review draft button) — that is the CSM's review
        # surface. acting_slack_user_id also scopes Slack-search evidence to the CSM.
        await draft_generation_tool(
            str(workspace_id),
            str(question_id),
            acting_slack_user_id=csm_slack_user_id,
        )
    except Exception:
        logger.exception("generate_draft_for_question: error for question %s", question_id)
        if slack_client:
            try:
                await slack_client.chat_postMessage(
                    channel=csm_slack_user_id,
                    text=":x: Drafting failed for that question — try *Generate draft* again from the RELAY *Home* tab. If it keeps failing, flag it to an admin.",
                )
            except Exception:
                logger.warning(
                    "generate_draft_for_question: failure notify failed for question %s",
                    question_id,
                    exc_info=True,
                )
        raise

    # Push the update immediately instead of leaving the CSM to guess when to refresh.
    if slack_client:
        try:
            from relay.slack.home import render_and_publish_home

            await render_and_publish_home(slack_client, workspace.slack_team_id, csm_slack_user_id)
            await slack_client.chat_postMessage(
                channel=csm_slack_user_id,
                text=":memo: Your draft is ready — check the RELAY *Home* tab under *Drafts Ready for Review*.",
            )
        except Exception:
            logger.warning(
                "generate_draft_for_question: post-generation notify failed for question %s",
                question_id,
                exc_info=True,
            )
