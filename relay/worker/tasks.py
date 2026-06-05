"""Celery tasks for async Slack event processing."""

import logging

from relay.worker.celery_app import celery
from relay.worker.hubspot_tasks import sync_hubspot_accounts  # noqa: F401

logger = logging.getLogger(__name__)


def make_dedup_key(team_id: str, channel_id: str, message_ts: str) -> str:
    return f"event:{team_id}:{channel_id}:{message_ts}"


@celery.task(bind=True, max_retries=3)
def process_slack_event(self, payload: dict) -> None:
    team_id = payload.get("team_id", "")
    event = payload.get("event", {})
    channel_id = event.get("channel", "")
    message_ts = event.get("ts", "")
    dedup_key = make_dedup_key(team_id, channel_id, message_ts)
    logger.info("Received Slack event dedup_key=%s subtype=%s", dedup_key, event.get("subtype"))

