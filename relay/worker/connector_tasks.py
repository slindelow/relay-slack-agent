"""Celery tasks for source connector syncing."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from relay.connectors import registry
from relay.db.models import SourceConnector
from relay.db.session import get_session
from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="relay.sync_connector", bind=True, max_retries=0)
def sync_connector(self, workspace_id_str: str, connector_id_str: str) -> None:
    """Sync a single source connector. Args are strings for JSON serialization."""
    asyncio.run(_sync_connector_async(uuid.UUID(workspace_id_str), uuid.UUID(connector_id_str)))


async def _sync_connector_async(workspace_id: uuid.UUID, connector_id: uuid.UUID) -> None:
    connector_type = await _mark_connector_syncing(workspace_id, connector_id)
    if connector_type is None:
        logger.warning("sync_connector: connector %s not found", connector_id)
        return

    connector = registry.get_connector(connector_type)
    try:
        await connector.sync(workspace_id, connector_id)
    except Exception:
        await _mark_connector_finished(workspace_id, connector_id, "error")
        logger.exception("sync_connector: error syncing %s", connector_id)
        return

    await _mark_connector_finished(workspace_id, connector_id, "synced", datetime.now(UTC))
    logger.info("sync_connector: synced %s for workspace %s", connector_id, workspace_id)


async def _mark_connector_syncing(workspace_id: uuid.UUID, connector_id: uuid.UUID) -> str | None:
    async with get_session(workspace_id) as session:
        result = await session.execute(
            select(SourceConnector).where(
                SourceConnector.workspace_id == workspace_id,
                SourceConnector.id == connector_id,
                SourceConnector.disconnected_at.is_(None),
            )
        )
        connector_row = result.scalar_one_or_none()
        if connector_row is None:
            return None

        connector_row.sync_status = "syncing"
        return connector_row.connector_type


async def _mark_connector_finished(
    workspace_id: uuid.UUID,
    connector_id: uuid.UUID,
    sync_status: str,
    last_synced_at: datetime | None = None,
) -> None:
    async with get_session(workspace_id) as session:
        result = await session.execute(
            select(SourceConnector).where(
                SourceConnector.workspace_id == workspace_id,
                SourceConnector.id == connector_id,
            )
        )
        connector_row = result.scalar_one_or_none()
        if connector_row is None:
            logger.warning("sync_connector: connector %s disappeared before finish", connector_id)
            return

        connector_row.sync_status = sync_status
        if last_synced_at is not None:
            connector_row.last_synced_at = last_synced_at


@celery.task(name="relay.sync_all_connectors")
def sync_all_connectors() -> None:
    """Enqueue sync_connector for every active source connector."""
    asyncio.run(_sync_all_connectors_async())


async def _sync_all_connectors_async() -> None:
    async with get_session() as session:
        result = await session.execute(
            select(SourceConnector.id, SourceConnector.workspace_id).where(
                SourceConnector.disconnected_at.is_(None)
            )
        )
        rows = result.fetchall()

    for row in rows:
        sync_connector.delay(str(row.workspace_id), str(row.id))
        logger.info("sync_all_connectors: enqueued connector %s", row.id)
