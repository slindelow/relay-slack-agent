"""Slack settings view — connector management and purge (Plan 7 US-003)."""

from __future__ import annotations

import logging
import uuid

from relay.slack.app import app

logger = logging.getLogger(__name__)


def _settings_blocks(connectors: list) -> list:
    """Build settings view blocks listing active connectors with Disconnect+Purge buttons."""
    if not connectors:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No source connectors configured. Use App Home to add connectors.",
                },
            }
        ]

    blocks: list = [
        {"type": "header", "text": {"type": "plain_text", "text": "Source Connectors"}},
    ]
    for connector in connectors:
        provider_label = (connector.connector_type or "").replace("_", " ").title()
        last_sync = connector.last_synced_at.strftime("%Y-%m-%d %H:%M") if connector.last_synced_at else "Never"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{provider_label}*\nLast synced: {last_sync}",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Disconnect + Purge"},
                    "style": "danger",
                    "action_id": "relay_disconnect_connector",
                    "value": str(connector.id),
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Disconnect connector?"},
                        "text": {
                            "type": "mrkdwn",
                            "text": f"This will remove *{provider_label}* and delete all indexed content. This cannot be undone.",
                        },
                        "confirm": {"type": "plain_text", "text": "Disconnect + Purge"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                },
            }
        )
    return blocks


@app.action("relay_disconnect_connector")
async def relay_disconnect_connector(ack, body, respond):
    await ack()

    actions = body.get("actions", [])
    connector_id_str = actions[0].get("value", "") if actions else ""
    team_id = body.get("team", {}).get("id", "") or body.get("team_id", "")

    try:
        connector_id = uuid.UUID(connector_id_str)
    except ValueError:
        logger.warning("relay_disconnect_connector: invalid connector_id %r", connector_id_str)
        return

    try:
        from datetime import UTC, datetime
        from sqlalchemy import delete, select, update
        from relay.db.models import KnowledgeChunk, SourceConnector, SourceDocument, Workspace
        from relay.db.session import get_session

        async with get_session() as unscoped:
            ws_result = await unscoped.execute(
                select(Workspace).where(Workspace.slack_team_id == team_id)
            )
            workspace = ws_result.scalar_one_or_none()

        if workspace is None:
            return

        async with get_session(workspace.id) as session:
            # Load connector to get its type for the confirmation message
            conn_result = await session.execute(
                select(SourceConnector).where(
                    SourceConnector.id == connector_id,
                    SourceConnector.workspace_id == workspace.id,
                )
            )
            connector = conn_result.scalar_one_or_none()
            if connector is None:
                return

            provider_label = connector.connector_type.replace("_", " ").title()

            # Delete knowledge_chunks for source documents of this connector
            doc_result = await session.execute(
                select(SourceDocument.id).where(
                    SourceDocument.connector_id == connector_id,
                    SourceDocument.workspace_id == workspace.id,
                )
            )
            doc_ids = [row[0] for row in doc_result.fetchall()]

            if doc_ids:
                await session.execute(
                    delete(KnowledgeChunk).where(
                        KnowledgeChunk.source_document_id.in_(doc_ids),
                        KnowledgeChunk.workspace_id == workspace.id,
                    )
                )

            # Delete source documents
            await session.execute(
                delete(SourceDocument).where(
                    SourceDocument.connector_id == connector_id,
                    SourceDocument.workspace_id == workspace.id,
                )
            )

            # Mark connector disconnected
            await session.execute(
                update(SourceConnector)
                .where(
                    SourceConnector.id == connector_id,
                    SourceConnector.workspace_id == workspace.id,
                )
                .values(disconnected_at=datetime.now(UTC))
            )

            await session.commit()

        await respond(
            response_type="ephemeral",
            text=f"{provider_label} disconnected. All indexed content removed.",
        )
        logger.info(
            "Connector %s purged for workspace_id=%s", connector_id, workspace.id
        )
    except Exception:
        logger.exception(
            "relay_disconnect_connector: error purging connector_id=%s", connector_id_str
        )
        await respond(
            response_type="ephemeral",
            text="An error occurred while disconnecting the connector. Please try again.",
        )
