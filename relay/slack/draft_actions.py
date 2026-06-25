"""Bolt action and view handlers for draft lifecycle (US-005 – US-008)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from relay.slack.app import app
from relay.db.session import get_session

logger = logging.getLogger(__name__)


async def _resolve_workspace_id(team_id: str) -> uuid.UUID | None:
    if not team_id:
        return None

    from sqlalchemy import select
    from relay.db.models import Workspace

    async with get_session() as unscoped:
        ws_result = await unscoped.execute(
            select(Workspace).where(Workspace.slack_team_id == team_id)
        )
        workspace = ws_result.scalar_one_or_none()
    return workspace.id if workspace else None


async def _require_csm_for_workspace(workspace_id: uuid.UUID, slack_user_id: str) -> bool:
    if not slack_user_id:
        return False

    from relay.auth import require_relay_csm

    async with get_session(workspace_id) as session:
        return await require_relay_csm(session, workspace_id, slack_user_id)


def _build_customer_response_text(response_body: str, actor) -> str:
    """Format approved draft text for the customer channel."""
    display_name = (getattr(actor, "display_name", "") or "").strip()
    if display_name:
        return f"From {display_name} via RELAY:\n\n{response_body}"
    return f"From your customer success team via RELAY:\n\n{response_body}"


# ---------------------------------------------------------------------------
# US-005: Open draft review modal
# ---------------------------------------------------------------------------


@app.action("relay_open_draft_modal")
async def handle_open_draft_modal(ack, body, client):
    await ack()

    actions = body.get("actions", [])
    draft_id_str = actions[0].get("value", "") if actions else ""
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")
    trigger_id = body.get("trigger_id", "")

    try:
        draft_id = uuid.UUID(draft_id_str)
    except ValueError:
        logger.warning("relay_open_draft_modal: invalid draft_id %r", draft_id_str)
        return

    try:
        from sqlalchemy import select
        from relay.db.models import CustomerAccount, Draft, MonitoredChannel, Question
        from relay.db.session import get_session
        from relay.slack.draft_modal import build_draft_modal

        workspace_id = await _resolve_workspace_id(team_id)
        if workspace_id is None:
            return
        if not await _require_csm_for_workspace(workspace_id, user_id):
            logger.warning(
                "relay_open_draft_modal: unauthorized open attempt by %s for draft %s",
                user_id,
                draft_id,
            )
            return

        async with get_session(workspace_id) as session:
            draft_result = await session.execute(
                select(Draft).where(Draft.workspace_id == workspace_id, Draft.id == draft_id)
            )
            draft = draft_result.scalar_one_or_none()
            if draft is None:
                return

            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == draft.question_id,
                )
            )
            question = q_result.scalar_one_or_none()

            account = None
            if question and question.channel_id:
                ch_result = await session.execute(
                    select(MonitoredChannel).where(
                        MonitoredChannel.workspace_id == workspace_id,
                        MonitoredChannel.id == question.channel_id,
                    )
                )
                channel = ch_result.scalar_one_or_none()
                if channel and channel.account_id:
                    acct_result = await session.execute(
                        select(CustomerAccount).where(
                            CustomerAccount.workspace_id == workspace_id,
                            CustomerAccount.id == channel.account_id,
                        )
                    )
                    account = acct_result.scalar_one_or_none()

            modal = build_draft_modal(draft, question, account)

        await client.views_open(trigger_id=trigger_id, view=modal)

    except Exception:
        logger.exception("relay_open_draft_modal: error for draft %s", draft_id_str)


# ---------------------------------------------------------------------------
# US-008: Generate draft from App Home button
# ---------------------------------------------------------------------------


@app.action("relay_generate_draft")
async def handle_generate_draft(ack, body, respond):
    await ack()

    actions = body.get("actions", [])
    question_id_str = actions[0].get("value", "") if actions else ""
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    user_id = body.get("user", {}).get("id", "")

    try:
        question_id = uuid.UUID(question_id_str)
    except ValueError:
        logger.warning("relay_generate_draft: invalid question_id %r", question_id_str)
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Question
        from relay.db.session import get_session
        from relay.worker.drafting_tasks import generate_draft_for_question

        workspace_id = await _resolve_workspace_id(team_id)
        if workspace_id is None:
            return
        if not await _require_csm_for_workspace(workspace_id, user_id):
            logger.warning(
                "relay_generate_draft: unauthorized generate attempt by %s for question %s",
                user_id,
                question_id,
            )
            return

        async with get_session(workspace_id) as session:
            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == question_id,
                )
            )
            if q_result.scalar_one_or_none() is None:
                return

        generate_draft_for_question.delay(str(workspace_id), str(question_id), user_id)

        await respond(
            response_type="ephemeral",
            text="Draft generation started — I'll DM you a *Review draft* button when it's ready.",
        )
    except Exception:
        logger.exception("relay_generate_draft: error for question %s", question_id_str)


# ---------------------------------------------------------------------------
# US-006: Send approved response
# ---------------------------------------------------------------------------


@app.view("relay_send_draft")
async def handle_send_draft(ack, body, client):
    await ack()

    user_id = body.get("user", {}).get("id", "")
    view = body.get("view", {})
    private_meta = json.loads(view.get("private_metadata", "{}"))
    draft_id_str = private_meta.get("draft_id", "")
    workspace_id_str = private_meta.get("workspace_id", "")

    response_body = (
        view.get("state", {})
        .get("values", {})
        .get("response_body", {})
        .get("response_body_value", {})
        .get("value", "")
    ) or ""

    try:
        draft_id = uuid.UUID(draft_id_str)
        workspace_id = uuid.UUID(workspace_id_str)
    except ValueError:
        logger.warning("relay_send_draft: invalid IDs in private_metadata")
        return

    try:
        from sqlalchemy import select
        from relay.db.models import (
            Assignment, Draft, ImpactMetric, MonitoredChannel,
            Question, QuestionEvent, SlaPolicy, User,
        )
        from relay.drafting.memory import index_approved_response
        from relay.question.machine import resolve_question

        async with get_session(workspace_id) as session:
            # Load draft
            draft_result = await session.execute(
                select(Draft).where(Draft.workspace_id == workspace_id, Draft.id == draft_id)
            )
            draft = draft_result.scalar_one_or_none()
            if draft is None:
                logger.warning("relay_send_draft: draft %s not found", draft_id)
                return

            # Role check — only admin / csm may send drafts
            from relay.auth import require_relay_csm
            is_authorized = await require_relay_csm(session, workspace_id, user_id)
            if not is_authorized:
                logger.warning(
                    "relay_send_draft: unauthorized send attempt by %s for draft %s",
                    user_id, draft_id,
                )
                return

            # Load question
            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == draft.question_id,
                )
            )
            question = q_result.scalar_one_or_none()

            # Find customer channel
            channel_id_slack = None
            if question and question.channel_id:
                ch_result = await session.execute(
                    select(MonitoredChannel).where(
                        MonitoredChannel.workspace_id == workspace_id,
                        MonitoredChannel.id == question.channel_id,
                    )
                )
                channel = ch_result.scalar_one_or_none()
                if channel:
                    channel_id_slack = channel.slack_channel_id

            # Empty body guard
            if not response_body.strip():
                logger.warning("relay_send_draft: empty response_body, aborting send")
                return

            # Resolve approver User
            actor_result = await session.execute(
                select(User).where(User.workspace_id == workspace_id, User.slack_user_id == user_id)
            )
            actor = actor_result.scalar_one_or_none()
            actor_id = actor.id if actor else None

            # Post to customer channel
            if channel_id_slack:
                message_text = _build_customer_response_text(response_body, actor)
                await client.chat_postMessage(channel=channel_id_slack, text=message_text)

            # Update draft
            now = datetime.now(UTC)
            draft.status = "sent"
            draft.approved_by_user_id = actor_id
            draft.sent_at = now

            # Resolve question
            if question and actor_id:
                try:
                    await resolve_question(session, question.id, actor_id)
                except Exception:
                    pass

            # QuestionEvent
            if question:
                session.add(QuestionEvent(
                    workspace_id=workspace_id,
                    question_id=question.id,
                    event_type="response_sent",
                    actor_user_id=actor_id,
                ))

            # ImpactMetric
            sla_met = None
            if question:
                time_to_send = int((now - question.created_at).total_seconds()) if question.created_at else None
                if question.next_alert_at:
                    sla_met = now <= question.next_alert_at
                session.add(ImpactMetric(
                    workspace_id=workspace_id,
                    question_id=question.id,
                    draft_id=draft_id,
                    time_to_send_seconds=time_to_send,
                    draft_accepted=True,
                    sla_met=sla_met,
                ))
                try:
                    draft.customer_draft = response_body  # persist the final approved text
                    await index_approved_response(
                        workspace_id=workspace_id,
                        question_id=question.id,
                        draft_id=draft_id,
                        session=session,
                    )
                except Exception:
                    logger.warning("index_approved_response failed; response was sent", exc_info=True)

        # Notify CSM
        channel_name = f"<#{channel_id_slack}>" if channel_id_slack else "the customer channel"
        await client.chat_postMessage(
            channel=user_id,
            text=f":white_check_mark: Response sent to {channel_name}",
        )

    except Exception:
        logger.exception("relay_send_draft: error for draft %s", draft_id_str)


# ---------------------------------------------------------------------------
# US-007: Discard draft
# ---------------------------------------------------------------------------


@app.action("relay_discard_draft")
async def handle_discard_draft(ack, body, client):
    await ack()

    actions = body.get("actions", [])
    draft_id_str = actions[0].get("value", "") if actions else ""
    user_id = body.get("user", {}).get("id", "")
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")

    try:
        draft_id = uuid.UUID(draft_id_str)
    except ValueError:
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Draft, FeedbackSignal, ImpactMetric, User
        from relay.db.session import get_session

        workspace_id = await _resolve_workspace_id(team_id)
        if workspace_id is None:
            return
        async with get_session(workspace_id) as session:
            draft_result = await session.execute(
                select(Draft).where(Draft.workspace_id == workspace_id, Draft.id == draft_id)
            )
            draft = draft_result.scalar_one_or_none()
            if draft is None:
                return
            from relay.auth import require_relay_csm
            if not await require_relay_csm(session, workspace_id, user_id):
                logger.warning(
                    "relay_discard_draft: unauthorized discard attempt by %s for draft %s",
                    user_id,
                    draft_id,
                )
                return

            actor_result = await session.execute(
                select(User).where(User.workspace_id == workspace_id, User.slack_user_id == user_id)
            )
            actor = actor_result.scalar_one_or_none()
            actor_id = actor.id if actor else None

            draft.status = "discarded"

            session.add(FeedbackSignal(
                workspace_id=workspace_id,
                question_id=draft.question_id,
                draft_id=draft_id,
                actor_user_id=actor_id,
                correction_action="discard_draft",
            ))

            session.add(ImpactMetric(
                workspace_id=workspace_id,
                question_id=draft.question_id,
                draft_id=draft_id,
                draft_accepted=False,
                sla_met=None,
            ))

    except Exception:
        logger.exception("relay_discard_draft: error for draft %s", draft_id_str)


# ---------------------------------------------------------------------------
# US-007: Regenerate draft
# ---------------------------------------------------------------------------


@app.action("relay_regenerate_draft")
async def handle_regenerate_draft(ack, body, client):
    await ack()

    actions = body.get("actions", [])
    draft_id_str = actions[0].get("value", "") if actions else ""
    user_id = body.get("user", {}).get("id", "")
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")

    try:
        draft_id = uuid.UUID(draft_id_str)
    except ValueError:
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Draft, FeedbackSignal, User
        from relay.db.session import get_session
        from relay.worker.drafting_tasks import generate_draft_for_question

        workspace_id = await _resolve_workspace_id(team_id)
        if workspace_id is None:
            return
        question_id: uuid.UUID | None = None
        async with get_session(workspace_id) as session:
            draft_result = await session.execute(
                select(Draft).where(Draft.workspace_id == workspace_id, Draft.id == draft_id)
            )
            draft = draft_result.scalar_one_or_none()
            if draft is None:
                return
            from relay.auth import require_relay_csm
            if not await require_relay_csm(session, workspace_id, user_id):
                logger.warning(
                    "relay_regenerate_draft: unauthorized regenerate attempt by %s for draft %s",
                    user_id,
                    draft_id,
                )
                return

            actor_result = await session.execute(
                select(User).where(User.workspace_id == workspace_id, User.slack_user_id == user_id)
            )
            actor = actor_result.scalar_one_or_none()
            actor_id = actor.id if actor else None

            question_id = draft.question_id
            draft.status = "discarded"

            session.add(FeedbackSignal(
                workspace_id=workspace_id,
                question_id=question_id,
                draft_id=draft_id,
                actor_user_id=actor_id,
                correction_action="regenerate_draft",
            ))

        if question_id:
            generate_draft_for_question.delay(str(workspace_id), str(question_id))

        await client.chat_postMessage(
            channel=user_id,
            text="Regenerating — you'll get a new draft shortly.",
        )

    except Exception:
        logger.exception("relay_regenerate_draft: error for draft %s", draft_id_str)


# ---------------------------------------------------------------------------
# Export feedback — no-op ack (URL handles the click; ack prevents Bolt warning)
# ---------------------------------------------------------------------------


@app.action("relay_export_feedback")
async def handle_export_feedback_action(ack):
    await ack()
