"""Slack interactive action handlers for question lifecycle actions.

Handles the four Block Kit buttons from alert DMs:
  relay_claim_question    — open/detected → claimed
  relay_snooze_1h         — suppress alerts for 1 hour
  relay_snooze_4h         — suppress alerts for 4 hours
  relay_mark_not_question — close question as not-a-question (resolves with note)

All handlers ack immediately and run DB work synchronously within the async
Bolt handler (no Celery needed — these are user-initiated, low-volume ops).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from relay.slack.app import app  # noqa: E402 (circular import resolved at load time)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_question_id(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


def _get_question_id_from_action(body: dict) -> uuid.UUID | None:
    """Extract the question UUID from the Bolt action body."""
    actions = body.get("actions", [])
    if not actions:
        return None
    return _parse_question_id(actions[0].get("value", ""))


async def _get_or_create_user(session, workspace_id: uuid.UUID, slack_user_id: str):
    """Return User for slack_user_id, creating a stub row if not yet seen."""
    from sqlalchemy import select
    from relay.db.models import User

    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            workspace_id=workspace_id,
            slack_user_id=slack_user_id,
        )
        session.add(user)
        await session.flush()
    return user


# ---------------------------------------------------------------------------
# Action: Claim question
# ---------------------------------------------------------------------------


@app.action("relay_claim_question")
async def handle_claim_question(ack, body, respond, logger=logger):
    """Transition question from open/detected → claimed.

    Sets claimed_at, records a QuestionEvent, ephemeral confirmation.
    """
    await ack()

    question_id = _get_question_id_from_action(body)
    if question_id is None:
        await respond(text="⚠️ Could not parse question ID.", response_type="ephemeral")
        return

    team_id = body.get("team", {}).get("id", "")
    actor_slack_id = body.get("user", {}).get("id", "")

    try:
        from sqlalchemy import select
        from relay.db.models import Question, QuestionState, Workspace
        from relay.db.session import get_session

        # Step 1: resolve workspace from Slack team_id (unscoped — Workspace table has no RLS)
        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(text="⚠️ Workspace not found.", response_type="ephemeral")
            return

        workspace_id = workspace.id

        # Step 2: all further queries use the RLS-enforced scoped session
        async with get_session(workspace_id) as session:
            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == question_id,
                )
            )
            question = q_result.scalar_one_or_none()

            if question is None:
                await respond(text="⚠️ Question not found.", response_type="ephemeral")
                return

            actor = await _get_or_create_user(session, workspace_id, actor_slack_id)

            from relay.question.machine import claim_question, InvalidStateTransition
            try:
                await claim_question(session, question_id, actor.id)
            except InvalidStateTransition as exc:
                await respond(
                    text=f"⚠️ Cannot claim: question is already *{exc.from_state}*.",
                    response_type="ephemeral",
                )
                return

        await respond(
            text=f"✅ You've claimed this question. It's now yours to answer.",
            response_type="ephemeral",
        )

    except Exception:
        logger.exception("handle_claim_question: unexpected error for question %s", question_id)
        await respond(text="⚠️ An error occurred. Please try again.", response_type="ephemeral")


# ---------------------------------------------------------------------------
# Action: Snooze question (shared logic, two button variants)
# ---------------------------------------------------------------------------


async def _handle_snooze(ack, body, respond, hours: int, logger=logger):
    await ack()

    question_id = _get_question_id_from_action(body)
    if question_id is None:
        await respond(text="⚠️ Could not parse question ID.", response_type="ephemeral")
        return

    team_id = body.get("team", {}).get("id", "")
    actor_slack_id = body.get("user", {}).get("id", "")
    snoozed_until = datetime.now(UTC) + timedelta(hours=hours)

    try:
        from sqlalchemy import select
        from relay.db.models import Question, Snooze, Workspace
        from relay.db.session import get_session

        # Step 1: resolve workspace from Slack team_id (unscoped — Workspace table has no RLS)
        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(text="⚠️ Workspace not found.", response_type="ephemeral")
            return

        workspace_id = workspace.id

        # Step 2: all further queries use the RLS-enforced scoped session
        async with get_session(workspace_id) as session:
            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == question_id,
                )
            )
            question = q_result.scalar_one_or_none()

            if question is None:
                await respond(text="⚠️ Question not found.", response_type="ephemeral")
                return

            actor = await _get_or_create_user(session, workspace_id, actor_slack_id)
            session.add(Snooze(
                workspace_id=workspace_id,
                question_id=question_id,
                snoozed_by_user_id=actor.id,
                snoozed_until=snoozed_until,
                reason=f"Snoozed {hours}h via alert button",
            ))
            # Advance next_alert_at so the poller doesn't fire before snooze lifts
            q2_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == question_id,
                )
            )
            q2 = q2_result.scalar_one_or_none()
            if q2:
                q2.next_alert_at = snoozed_until

        label = f"{hours}h" if hours < 24 else f"{hours // 24}d"
        await respond(
            text=f"😴 Snoozed for {label}. You'll be reminded at <!date^{int(snoozed_until.timestamp())}^{{time}} on {{date_short}}|{snoozed_until.strftime('%H:%M %Z')}>.",
            response_type="ephemeral",
        )

    except Exception:
        logger.exception("handle_snooze_%dh: error for question %s", hours, question_id)
        await respond(text="⚠️ An error occurred. Please try again.", response_type="ephemeral")


@app.action("relay_snooze_1h")
async def handle_snooze_1h(ack, body, respond, logger=logger):
    await _handle_snooze(ack, body, respond, hours=1, logger=logger)


@app.action("relay_snooze_4h")
async def handle_snooze_4h(ack, body, respond, logger=logger):
    await _handle_snooze(ack, body, respond, hours=4, logger=logger)


# ---------------------------------------------------------------------------
# Action: Mark not a question
# ---------------------------------------------------------------------------


@app.action("relay_mark_not_question")
async def handle_mark_not_question(ack, body, respond, logger=logger):
    """Resolve question as 'not a question' — suppresses further alerts."""
    await ack()

    question_id = _get_question_id_from_action(body)
    if question_id is None:
        await respond(text="⚠️ Could not parse question ID.", response_type="ephemeral")
        return

    team_id = body.get("team", {}).get("id", "")
    actor_slack_id = body.get("user", {}).get("id", "")

    try:
        from sqlalchemy import select
        from relay.db.models import Question, Workspace
        from relay.db.session import get_session

        # Step 1: resolve workspace from Slack team_id (unscoped — Workspace table has no RLS)
        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(text="⚠️ Workspace not found.", response_type="ephemeral")
            return

        workspace_id = workspace.id

        # Step 2: all further queries use the RLS-enforced scoped session
        async with get_session(workspace_id) as session:
            q_result = await session.execute(
                select(Question).where(
                    Question.workspace_id == workspace_id,
                    Question.id == question_id,
                )
            )
            question = q_result.scalar_one_or_none()

            if question is None:
                await respond(text="⚠️ Question not found.", response_type="ephemeral")
                return

            actor = await _get_or_create_user(session, workspace_id, actor_slack_id)

            from relay.question.machine import resolve_question, InvalidStateTransition
            try:
                await resolve_question(session, question_id, actor.id)
            except InvalidStateTransition as exc:
                if exc.from_state in ("resolved", "expired"):
                    # Already closed — idempotent OK
                    pass
                else:
                    await respond(
                        text=f"⚠️ Cannot close: question is *{exc.from_state}*.",
                        response_type="ephemeral",
                    )
                    return

        await respond(
            text="✅ Marked as not a question. Alerts suppressed.",
            response_type="ephemeral",
        )

    except Exception:
        logger.exception("handle_mark_not_question: error for question %s", question_id)
        await respond(text="⚠️ An error occurred. Please try again.", response_type="ephemeral")
