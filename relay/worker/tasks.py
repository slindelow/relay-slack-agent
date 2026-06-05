"""Celery tasks for async Slack event processing."""

import asyncio
import logging

from relay.worker.celery_app import celery
from relay.worker.hubspot_tasks import sync_hubspot_accounts  # noqa: F401

logger = logging.getLogger(__name__)


def make_dedup_key(team_id: str, channel_id: str, message_ts: str) -> str:
    return f"event:{team_id}:{channel_id}:{message_ts}"


@celery.task(name="relay.process_slack_event")
def process_slack_event(payload: dict) -> None:
    """Classify a Slack message and create a Question if warranted.

    Runs sync in Celery worker. Uses asyncio.run() for async DB/classifier calls.
    """
    asyncio.run(_process_slack_event_async(payload))


async def _process_slack_event_async(payload: dict) -> None:
    from sqlalchemy import select

    from relay.config import get_settings
    from relay.db.models import Message, MonitoredChannel, Question, QuestionState, QuestionUrgency
    from relay.db.session import get_session
    from classifier.classify import classify_message

    settings = get_settings()

    team_id = payload["team_id"]
    slack_channel_id = payload["channel_id"]
    ts = payload["ts"]
    sender_team_id = payload.get("team", team_id)
    text = payload.get("text", "")

    # Dedup check using make_dedup_key
    dedup_key = make_dedup_key(team_id, slack_channel_id, ts)
    # (Redis dedup is a TODO — log and continue for now)
    logger.debug("Processing event dedup_key=%s", dedup_key)

    # Use a session WITHOUT workspace context to look up the channel
    # (we don't know workspace_id from the raw event alone)
    async with get_session() as session:
        result = await session.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.slack_channel_id == slack_channel_id,
                MonitoredChannel.is_active.is_(True),
            )
        )
        channel = result.scalar_one_or_none()

    if channel is None:
        return  # Not a monitored channel

    workspace_id = channel.workspace_id

    # Determine if customer message
    is_customer = bool(
        channel.customer_slack_team_id
        and sender_team_id == channel.customer_slack_team_id
    )

    # Classify only customer messages
    if not is_customer:
        return

    # Classify
    result_cls = await classify_message(
        text,
        variant=settings.classifier_variant,
        model=settings.classifier_model,
    )

    # Persist Message record and optionally create Question
    async with get_session(workspace_id) as session:
        msg = Message(
            workspace_id=workspace_id,
            channel_id=channel.id,
            slack_message_ts=ts,
            sender_slack_user_id=payload.get("user"),
            sender_slack_team_id=sender_team_id,
            is_customer_message=True,
            raw_excerpt=text[:500],
            classification_label=result_cls.is_question,
            classification_confidence=result_cls.confidence,
            classification_variant=result_cls.variant,
        )
        session.add(msg)
        await session.flush()

        if result_cls.confidence >= settings.classifier_open_threshold:
            question = Question(
                workspace_id=workspace_id,
                channel_id=channel.id,
                message_id=msg.id,
                account_id=channel.account_id,
                state=QuestionState.open.value,
                urgency=QuestionUrgency.normal.value,
                title_excerpt=text[:255],
            )
            session.add(question)
        elif result_cls.confidence >= settings.classifier_candidate_threshold:
            question = Question(
                workspace_id=workspace_id,
                channel_id=channel.id,
                message_id=msg.id,
                account_id=channel.account_id,
                state=QuestionState.detected.value,
                urgency=QuestionUrgency.normal.value,
                title_excerpt=text[:255],
            )
            session.add(question)

