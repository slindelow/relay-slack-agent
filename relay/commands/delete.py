"""Workspace deletion command and confirmation handler."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from relay.db.models import Workspace
from relay.db.session import get_session
from relay.slack.app import app

logger = logging.getLogger(__name__)


def build_delete_workspace_modal(team_id: str, actor_slack_user_id: str) -> dict:
    return {
        "type": "modal",
        "callback_id": "relay_confirm_delete_workspace_data",
        "private_metadata": json.dumps({
            "team_id": team_id,
            "actor_slack_user_id": actor_slack_user_id,
        }),
        "title": {"type": "plain_text", "text": "Delete RELAY data"},
        "submit": {"type": "plain_text", "text": "Delete"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*This will permanently delete all RELAY data for your workspace.*\n\n"
                        "This cannot be undone."
                    ),
                },
            }
        ],
    }


async def handle_delete_workspace_data(ack, command, client=None, respond=None) -> None:
    await ack()
    team_id = command.get("team_id", "")
    actor = command.get("user_id", "")
    trigger_id = command.get("trigger_id", "")
    if not team_id or not trigger_id or client is None:
        if respond:
            await respond(response_type="ephemeral", text="Unable to open deletion confirmation.")
        return

    await client.views_open(
        trigger_id=trigger_id,
        view=build_delete_workspace_modal(team_id, actor),
    )


@app.view("relay_confirm_delete_workspace_data")
async def handle_confirm_delete_workspace_data(ack, body, client):
    await ack()
    metadata = json.loads(body.get("view", {}).get("private_metadata", "{}"))
    team_id = metadata.get("team_id", "")
    actor = metadata.get("actor_slack_user_id", "")

    if not team_id:
        return

    try:
        from relay.worker.deletion_tasks import create_workspace_deletion_job, delete_workspace_data

        async with get_session() as session:
            result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = result.scalar_one_or_none()
            if workspace is None:
                return

        job = await create_workspace_deletion_job(workspace.id, actor_slack_user_id=actor)
        delete_workspace_data.delay(str(workspace.id), str(job.id))

        if actor:
            await client.chat_postMessage(
                channel=actor,
                text="Workspace deletion started. RELAY data will be purged shortly.",
            )
    except Exception:
        logger.exception("delete_workspace_confirmation_failed team=%s", team_id)
