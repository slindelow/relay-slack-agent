"""Celery tasks for workspace and connector data deletion (Plan 7 US-002)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)

# Deletion cascade order — most-dependent tables first
_CASCADE_ORDER = [
    "knowledge_chunks",
    "knowledge_entries",
    "source_documents",
    "source_connectors",
    "retrieval_logs",
    "drafts",
    "impact_metrics",
    "feedback_signals",
    "alerts",
    "snoozes",
    "assignments",
    "question_events",
    "questions",
    "messages",
    "monitored_channels",
    "customer_accounts",
    "users",
    "workspace_tokens",
    "workspace_settings",
    "sla_policies",
    "crm_connections",
    "classification_feedback",
]


async def _run_deletion(workspace_id: uuid.UUID) -> None:
    from sqlalchemy import delete, insert, select, text, update
    from relay.db.engine import async_engine
    from relay.db.models import AuditLog, Workspace, WorkspaceDeletionJob, WorkspaceDeletionJobStatus

    job_id = uuid.uuid4()

    async with async_engine.begin() as conn:
        # Record job start
        await conn.execute(
            insert(WorkspaceDeletionJob).values(
                id=job_id,
                workspace_id=workspace_id,
                status=WorkspaceDeletionJobStatus.pending,
                started_at=datetime.now(UTC),
            )
        )

    try:
        # Write audit log before deletion (no session scoping — audit_log has no RLS)
        async with async_engine.begin() as conn:
            await conn.execute(
                insert(AuditLog).values(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    event_type="workspace_deleted",
                    created_at=datetime.now(UTC),
                )
            )

        # Delete each table in cascade order
        for table in _CASCADE_ORDER:
            async with async_engine.begin() as conn:
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id = :wid"),
                    {"wid": workspace_id},
                )
                logger.debug("Deleted rows from %s for workspace_id=%s", table, workspace_id)

        # Finally delete the workspace row itself
        async with async_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM workspaces WHERE id = :wid"),
                {"wid": workspace_id},
            )

        # Mark job complete
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE workspace_deletion_jobs SET status='complete', completed_at=:now WHERE id=:jid"
                ),
                {"now": datetime.now(UTC), "jid": job_id},
            )

        logger.info("Workspace deletion complete for workspace_id=%s", workspace_id)

    except Exception as exc:
        async with async_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE workspace_deletion_jobs SET status='failed', completed_at=:now WHERE id=:jid"
                ),
                {"now": datetime.now(UTC), "jid": job_id},
            )
        logger.exception("Workspace deletion failed for workspace_id=%s: %s", workspace_id, exc)
        raise


@celery.task(name="relay.delete_workspace_data", bind=True, max_retries=0)
def delete_workspace_data(self, workspace_id_str: str) -> None:
    workspace_id = uuid.UUID(workspace_id_str)
    asyncio.run(_run_deletion(workspace_id))
