"""Slack event handlers for message ingestion."""

from datetime import UTC, datetime

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


@app.event("app_uninstalled")
async def handle_app_uninstalled(event, body, logger):
    team_id = body.get("team_id") or event.get("team_id") or event.get("team")
    if not team_id:
        return

    try:
        from sqlalchemy import select

        from relay.db.models import Workspace, WorkspaceToken
        from relay.db.session import get_session
        from relay.worker.deletion_tasks import create_workspace_deletion_job, delete_workspace_data

        async with get_session() as session:
            result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = result.scalar_one_or_none()
            if workspace is None:
                return

        async with get_session(workspace.id) as session:
            token_result = await session.execute(
                select(WorkspaceToken).where(
                    WorkspaceToken.workspace_id == workspace.id,
                    WorkspaceToken.is_revoked.is_(False),
                )
            )
            for token in token_result.scalars():
                token.is_revoked = True
                token.revoked_at = datetime.now(UTC)

        job = await create_workspace_deletion_job(workspace.id)
        delete_workspace_data.delay(str(workspace.id), str(job.id))
    except Exception:
        logger.exception("app_uninstalled_cleanup_failed team=%s", team_id)
