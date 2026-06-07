"""App Home view builder for RELAY."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from relay.slack.app import app

logger = logging.getLogger(__name__)

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

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Disconnect + Purge"},
                "action_id": "relay_disconnect_purge_connector",
                "value": str(row.id),
                "style": "danger",
            },
        })

    return blocks


def _draft_queue_blocks(questions_needing_draft: list[Any]) -> list[dict]:
    """Build blocks for claimed questions that have no pending/approved draft."""
    if not questions_needing_draft:
        return []

    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": "Questions Needing Drafts"}},
    ]
    for q in questions_needing_draft:
        body_excerpt = (q.title_excerpt or "")[:120]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":speech_balloon: _{body_excerpt}…_"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Generate draft"},
                "action_id": "relay_generate_draft",
                "value": str(q.id),
            },
        })
    return blocks


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"


def _rate(true_count: int, total_count: int) -> str:
    if total_count == 0:
        return "n/a"
    return f"{(true_count / total_count) * 100:.1f}%"


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2)


def _impact_blocks(impact_rows: list[Any]) -> list[dict]:
    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": "Impact"}},
    ]

    if not impact_rows:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "No data yet — stats appear after your first sent response."},
        })
        return blocks

    sla_values = [row.sla_met for row in impact_rows if row.sla_met is not None]
    accepted_values = [row.draft_accepted for row in impact_rows if row.draft_accepted is not None]
    send_times = [
        row.time_to_send_seconds
        for row in impact_rows
        if row.time_to_send_seconds is not None
    ]

    sla_rate = _rate(sum(1 for value in sla_values if value), len(sla_values))
    accepted_rate = _rate(sum(1 for value in accepted_values if value), len(accepted_values))
    median_send = _format_duration(_median(send_times))

    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*SLA met rate*\n{sla_rate}"},
            {"type": "mrkdwn", "text": f"*Draft accepted rate*\n{accepted_rate}"},
            {"type": "mrkdwn", "text": f"*Median time to send*\n{median_send}"},
            {"type": "mrkdwn", "text": f"*Questions handled*\n{len(impact_rows)}"},
        ],
    })
    return blocks


def _accuracy_blocks(feedback_rows: list[Any], total_questions: int, export_url: str) -> list[dict]:
    blocks: list[dict] = [
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": "Accuracy"}},
    ]

    corrections = sum(1 for row in feedback_rows if row.correction_action == "mark_not_question")

    button: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": "Export feedback"},
        "action_id": "relay_export_feedback",
    }
    if export_url.startswith("https://") or export_url.startswith("http://"):
        button["url"] = export_url

    if corrections == 0:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "No corrections this week — great accuracy!"},
            "accessory": button,
        })
        return blocks

    if total_questions == 0:
        accuracy_pct = "n/a"
    else:
        accuracy = max(0.0, (total_questions - corrections) / total_questions * 100)
        accuracy_pct = f"{accuracy:.1f}%"
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Corrections this week*\n{corrections}"},
            {"type": "mrkdwn", "text": f"*Classification accuracy*\n{accuracy_pct}"},
        ],
        "accessory": button,
    })
    return blocks


def build_home(
    connector_rows: list[Any],
    questions_needing_draft: list[Any] | None = None,
    impact_rows: list[Any] | None = None,
    feedback_rows: list[Any] | None = None,
    total_questions_7d: int = 0,
    feedback_export_url: str = "",
) -> list[dict]:
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
    return (
        base_blocks
        + _connector_blocks(connector_rows)
        + _draft_queue_blocks(questions_needing_draft or [])
        + _impact_blocks(impact_rows or [])
        + _accuracy_blocks(feedback_rows or [], total_questions_7d, feedback_export_url)
    )


@app.event("app_home_opened")
async def publish_app_home(event, client, body):
    team_id: str = body.get("team_id", "")

    connector_rows: list[Any] = []
    questions_needing_draft: list[Any] = []
    impact_rows: list[Any] = []
    feedback_rows: list[Any] = []
    total_questions_7d = 0
    feedback_export_url = ""
    if team_id:
        try:
            from datetime import timedelta

            from sqlalchemy import func, select

            from relay.config import get_settings
            from relay.db.models import Draft, FeedbackSignal, ImpactMetric, Question, QuestionState, SourceConnector, Workspace
            from relay.db.session import get_session

            feedback_export_url = f"{get_settings().app_base_url}/relay/admin/feedback-export"

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

                    # Claimed questions with no pending/approved draft
                    active_draft_q_ids = select(Draft.question_id).where(
                        Draft.workspace_id == workspace.id,
                        Draft.status.in_(["pending", "approved"]),
                    )
                    q_result = await session.execute(
                        select(Question).where(
                            Question.workspace_id == workspace.id,
                            Question.state == QuestionState.claimed.value,
                            Question.id.notin_(active_draft_q_ids),
                        ).limit(10)
                    )
                    questions_needing_draft = list(q_result.scalars())

                    impact_result = await session.execute(
                        select(ImpactMetric)
                        .where(
                            ImpactMetric.workspace_id == workspace.id,
                            ImpactMetric.created_at >= datetime.now(UTC) - timedelta(days=30),
                        )
                        .order_by(ImpactMetric.created_at.desc())
                        .limit(500)
                    )
                    impact_rows = list(impact_result.scalars())

                    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
                    feedback_result = await session.execute(
                        select(FeedbackSignal)
                        .where(
                            FeedbackSignal.workspace_id == workspace.id,
                            FeedbackSignal.created_at >= seven_days_ago,
                            FeedbackSignal.correction_action == "mark_not_question",
                        )
                        .limit(500)
                    )
                    feedback_rows = list(feedback_result.scalars())

                    question_count_result = await session.execute(
                        select(func.count())
                        .select_from(Question)
                        .where(
                            Question.workspace_id == workspace.id,
                            Question.created_at >= seven_days_ago,
                        )
                    )
                    total_questions_7d = question_count_result.scalar_one()
        except Exception:
            logger.warning("publish_app_home: failed to render for user %s", event.get("user", "unknown"), exc_info=True)

    blocks = build_home(
        connector_rows,
        questions_needing_draft,
        impact_rows,
        feedback_rows,
        total_questions_7d,
        feedback_export_url,
    )
    await client.views_publish(
        user_id=event["user"],
        view={"type": "home", "blocks": blocks},
    )


@app.action("relay_disconnect_purge_connector")
async def handle_disconnect_purge_connector(ack, body, client):
    await ack()
    actions = body.get("actions", [])
    connector_id = actions[0].get("value", "") if actions else ""
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")
    trigger_id = body.get("trigger_id", "")
    if not connector_id or not team_id or not trigger_id:
        return

    await client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "relay_confirm_purge_connector",
            "private_metadata": json.dumps({"team_id": team_id, "connector_id": connector_id}),
            "title": {"type": "plain_text", "text": "Disconnect source"},
            "submit": {"type": "plain_text", "text": "Purge"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Disconnect this source and permanently remove all indexed content from RELAY?",
                    },
                }
            ],
        },
    )


@app.view("relay_confirm_purge_connector")
async def handle_confirm_purge_connector(ack, body, client):
    await ack()
    metadata = json.loads(body.get("view", {}).get("private_metadata", "{}"))
    team_id = metadata.get("team_id", "")
    connector_id_str = metadata.get("connector_id", "")
    user_id = body.get("user", {}).get("id", "")

    try:
        connector_id = uuid.UUID(connector_id_str)
    except ValueError:
        return

    try:
        from sqlalchemy import select

        from relay.auth import require_relay_admin
        from relay.db.models import Workspace
        from relay.db.session import get_session
        from relay.worker.connector_tasks import purge_connector

        async with get_session() as unscoped:
            result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = result.scalar_one_or_none()
            if workspace is None:
                return

        async with get_session(workspace_id=workspace.id) as auth_session:
            is_admin = await require_relay_admin(auth_session, workspace.id, user_id)

        if not is_admin:
            return

        purge_connector.delay(str(workspace.id), str(connector_id))
        if user_id:
            await client.chat_postMessage(
                channel=user_id,
                text="Source disconnected. All indexed content will be removed shortly.",
            )
    except Exception:
        return
