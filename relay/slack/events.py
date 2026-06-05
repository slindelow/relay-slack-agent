"""Slack event handlers for message ingestion."""

from relay.slack.app import app


@app.event("message")
async def handle_message(event, say, logger):
    """Ack is automatic in Bolt for events. Enqueue to Celery immediately."""
    # Skip subtypes (edits, deletes, bot messages)
    if event.get("subtype"):
        return

    team_id = event.get("team", "")
    channel_id = event.get("channel", "")
    ts = event.get("ts", "")

    if not (team_id and channel_id and ts):
        return

    # Enqueue to Celery — pass only minimal data
    from relay.worker.tasks import process_slack_event
    process_slack_event.delay({
        "team_id": team_id,
        "channel_id": channel_id,
        "ts": ts,
        "user": event.get("user", ""),
        "team": event.get("team_id", team_id),  # sender's team_id for customer detection
        "text": (event.get("text") or "")[:500],  # truncated excerpt
    })
