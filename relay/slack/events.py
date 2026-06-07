"""Slack event handlers for message ingestion."""

import logging

from relay.slack.app import app

logger = logging.getLogger(__name__)


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


@app.event("app_uninstalled")
async def handle_app_uninstalled(event, logger):
    """On uninstall: revoke tokens and enqueue workspace deletion."""
    team_id = event.get("team_id", "")
    if not team_id:
        return

    try:
        from datetime import UTC, datetime
        from sqlalchemy import select, update
        from relay.db.models import Workspace, WorkspaceToken
        from relay.db.session import get_session
        from relay.worker.deletion_tasks import delete_workspace_data

        async with get_session() as session:
            ws_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            return

        # Revoke all tokens immediately
        async with get_session(workspace.id) as session:
            await session.execute(
                update(WorkspaceToken)
                .where(WorkspaceToken.workspace_id == workspace.id)
                .values(is_revoked=True, revoked_at=datetime.now(UTC))
            )
            await session.commit()

        # Enqueue full deletion
        delete_workspace_data.delay(str(workspace.id))
        logger.info("app_uninstalled: enqueued deletion for team_id=%s", team_id)
    except Exception:
        logger.exception("app_uninstalled: failed to process for team_id=%s", team_id)
