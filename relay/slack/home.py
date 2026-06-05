"""App Home view builder for RELAY."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from relay.slack.app import app

_CONNECTOR_ICONS = {
    "google_drive": ":page_facing_up:",
    "github": ":octopus:",
}
_DEFAULT_ICON = ":electric_plug:"
_STALE_HOURS = 24


def _human_time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    delta = datetime.now(UTC) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _status_badge(sync_status: str) -> str:
    badges = {
        "synced": ":white_check_mark: synced",
        "syncing": ":arrows_counterclockwise: syncing",
        "error": ":x: error",
        "not_synced": ":white_circle: never synced",
    }
    return badges.get(sync_status, sync_status)


def _connector_blocks(connector_rows: list[Any]) -> list[dict]:
    """Build Block Kit blocks for the Connected Sources section."""
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Connected Sources"}},
    ]

    if not connector_rows:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No sources connected. Use `/relay settings` to add a source._"},
        })
        return blocks

    for row in connector_rows:
        icon = _CONNECTOR_ICONS.get(row.connector_type, _DEFAULT_ICON)
        time_ago = _human_time_ago(row.last_synced_at)
        badge = _status_badge(row.sync_status)
        display_name = row.connector_type.replace("_", " ").title()

        text = f"{icon} *{display_name}*\n{badge} · {time_ago}"

        is_stale = (
            row.last_synced_at is not None
            and (datetime.now(UTC) - row.last_synced_at).total_seconds() > _STALE_HOURS * 3600
        )
        if is_stale:
            text += "\n:warning: Last synced over 24h ago — retrieval may be stale."

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

    return blocks


def build_home(connector_rows: list[Any]) -> list[dict]:
    """Return the full App Home block list given a list of SourceConnector rows."""
    base_blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "RELAY"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Welcome to RELAY.*\nMonitor customer Slack Connect channels, detect unanswered questions, and get cited response drafts.",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Setup checklist*\n"
                    ":white_circle: Register a customer channel\n"
                    ":white_circle: Connect CRM and knowledge sources\n"
                    ":white_circle: Assign account owners"
                ),
            },
        },
        {"type": "divider"},
    ]
    return base_blocks + _connector_blocks(connector_rows)


@app.event("app_home_opened")
async def publish_app_home(event, client, body):
    team_id: str = body.get("team_id", "")

    connector_rows: list[Any] = []
    if team_id:
        try:
            from sqlalchemy import select

            from relay.db.models import SourceConnector, Workspace
            from relay.db.session import get_session

            async with get_session() as unscoped:
                ws_result = await unscoped.execute(
                    select(Workspace).where(Workspace.slack_team_id == team_id)
                )
                workspace = ws_result.scalar_one_or_none()

            if workspace:
                async with get_session(workspace.id) as session:
                    conn_result = await session.execute(
                        select(SourceConnector).where(
                            SourceConnector.workspace_id == workspace.id,
                            SourceConnector.disconnected_at.is_(None),
                        )
                    )
                    connector_rows = list(conn_result.scalars())
        except Exception:
            pass  # Degrade gracefully — Home still renders without connector data

    blocks = build_home(connector_rows)
    await client.views_publish(
        user_id=event["user"],
        view={"type": "home", "blocks": blocks},
    )
