"""Handler for /relay delete-workspace-data slash command (Plan 7 US-002)."""

from __future__ import annotations

import logging

from relay.slack.app import app

logger = logging.getLogger(__name__)

_CONFIRM_MODAL = {
    "type": "modal",
    "callback_id": "relay_confirm_delete_workspace",
    "title": {"type": "plain_text", "text": "Delete workspace data"},
    "submit": {"type": "plain_text", "text": "Delete permanently"},
    "close": {"type": "plain_text", "text": "Cancel"},
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":warning: *This will permanently delete all RELAY data for your workspace.*\n\n"
                    "This cannot be undone. All questions, drafts, knowledge entries, "
                    "and connector data will be removed."
                ),
            },
        }
    ],
}


async def handle_delete_workspace(ack, client, command, respond):
    await ack()

    team_id = command.get("team_id", "")
    slack_user_id = command.get("user_id", "")
    trigger_id = command.get("trigger_id", "")

    if not trigger_id:
        await respond(
            response_type="ephemeral",
            text="Could not open confirmation modal. Please try again.",
        )
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Workspace
        from relay.db.session import get_session
        from relay.auth import require_relay_admin

        async with get_session() as session:
            ws_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            await respond(response_type="ephemeral", text="RELAY workspace not found.")
            return

        async with get_session(workspace_id=workspace.id) as session:
            is_admin = await require_relay_admin(session, workspace.id, slack_user_id)

        if not is_admin:
            await respond(
                response_type="ephemeral",
                text=":no_entry: Only workspace admins can delete RELAY data.",
            )
            return

        await client.views_open(trigger_id=trigger_id, view=_CONFIRM_MODAL)
    except Exception:
        logger.exception("Failed to open delete-workspace confirmation modal")
        await respond(
            response_type="ephemeral",
            text="Could not open confirmation modal. Please try again.",
        )


@app.view("relay_confirm_delete_workspace")
async def relay_confirm_delete_workspace(ack, body):
    await ack()
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    slack_user_id = body.get("user", {}).get("id", "")
    if not team_id:
        return

    try:
        from sqlalchemy import select
        from relay.db.models import Workspace
        from relay.db.session import get_session
        from relay.auth import require_relay_admin
        from relay.worker.deletion_tasks import delete_workspace_data

        async with get_session() as session:
            result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = result.scalar_one_or_none()

        if workspace is None:
            return

        async with get_session(workspace_id=workspace.id) as session:
            is_admin = await require_relay_admin(session, workspace.id, slack_user_id)

        if not is_admin:
            logger.warning(
                "relay_confirm_delete_workspace: non-admin %s attempted deletion for team %s",
                slack_user_id, team_id,
            )
            return

        delete_workspace_data.delay(str(workspace.id))
        logger.info("Enqueued workspace deletion for workspace_id=%s", workspace.id)
    except Exception:
        logger.exception("Failed to enqueue workspace deletion for team_id=%s", team_id)
