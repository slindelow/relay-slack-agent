"""Handler logic for the /relay settings subcommand."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select

from relay.config import get_settings
from relay.db.models import CrmConnection, MonitoredChannel, SourceConnector, User, Workspace
from relay.db.session import get_session

logger = logging.getLogger(__name__)


@dataclass
class SettingsStatus:
    installed: bool
    admin_count: int = 0
    channel_count: int = 0
    crm_connected: bool = False
    source_count: int = 0
    app_base_url: str = ""


def _mark(done: bool) -> str:
    return ":white_check_mark:" if done else ":white_circle:"


def build_settings_blocks(status: SettingsStatus) -> list[dict]:
    """Build the setup status blocks shown by /relay settings."""
    install_line = f"{_mark(status.installed)} Slack app installed"
    admin_line = f"{_mark(status.admin_count > 0)} First RELAY admin configured"
    channel_line = f"{_mark(status.channel_count > 0)} Customer Slack Connect channel registered"
    crm_line = f"{_mark(status.crm_connected)} HubSpot connected"
    source_line = f"{_mark(status.source_count > 0)} Knowledge source connected"

    help_text = (
        "*Private beta setup*\n"
        f"{install_line}\n"
        f"{admin_line}\n"
        f"{channel_line}\n"
        f"{crm_line}\n"
        f"{source_line}"
    )

    actions = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Connect HubSpot"},
            "url": f"{status.app_base_url.rstrip('/')}/hubspot/install",
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Open install page"},
            "url": status.app_base_url.rstrip("/") or "https://relay.example.com",
        },
    ]

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*RELAY settings*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": help_text}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Register a customer channel*\n"
                    "`/relay register #channel Account Name enterprise @owner`"
                ),
            },
        },
        {"type": "actions", "elements": actions},
    ]


async def handle_settings(ack, respond, command) -> None:
    """Handle `/relay settings` with a workspace-scoped setup summary."""
    await ack()

    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to load settings: missing Slack workspace id.")
        return

    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()

        if workspace is None:
            await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
            return

        async with get_session(workspace_id=workspace.id) as session:
            admin_count = await _count(
                session,
                select(func.count())
                .select_from(User)
                .where(
                    User.workspace_id == workspace.id,
                    User.relay_role == "admin",
                    User.deleted_at.is_(None),
                ),
            )
            channel_count = await _count(
                session,
                select(func.count())
                .select_from(MonitoredChannel)
                .where(
                    MonitoredChannel.workspace_id == workspace.id,
                    MonitoredChannel.is_active.is_(True),
                ),
            )
            crm_count = await _count(
                session,
                select(func.count())
                .select_from(CrmConnection)
                .where(
                    CrmConnection.workspace_id == workspace.id,
                    CrmConnection.disconnected_at.is_(None),
                ),
            )
            source_count = await _count(
                session,
                select(func.count())
                .select_from(SourceConnector)
                .where(
                    SourceConnector.workspace_id == workspace.id,
                    SourceConnector.disconnected_at.is_(None),
                ),
            )

        status = SettingsStatus(
            installed=True,
            admin_count=admin_count,
            channel_count=channel_count,
            crm_connected=crm_count > 0,
            source_count=source_count,
            app_base_url=get_settings().app_base_url,
        )
    except Exception as exc:
        logger.exception("settings_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Settings failed: {type(exc).__name__}")
        return

    await respond(response_type="ephemeral", blocks=build_settings_blocks(status))


async def _count(session, statement) -> int:
    result = await session.execute(statement)
    return int(result.scalar_one() or 0)
