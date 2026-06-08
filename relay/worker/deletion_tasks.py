"""Marketplace deletion flows."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from relay.db.models import (
    Alert,
    Assignment,
    AuditLog,
    ClassificationFeedback,
    CrmConnection,
    CustomerAccount,
    Draft,
    FeedbackSignal,
    ImpactMetric,
    KnowledgeChunk,
    KnowledgeEntry,
    Message,
    MonitoredChannel,
    Question,
    QuestionEvent,
    RetrievalLog,
    SlaPolicy,
    Snooze,
    SourceConnector,
    SourceDocument,
    User,
    Workspace,
    WorkspaceDeletionJob,
    WorkspaceSettings,
    WorkspaceToken,
)
from relay.db.session import get_session
from relay.worker.celery_app import celery

_DELETE_ORDER = (
    KnowledgeChunk,
    RetrievalLog,
    FeedbackSignal,
    ImpactMetric,
    Alert,
    Snooze,
    Assignment,
    QuestionEvent,
    Draft,
    KnowledgeEntry,
    SourceDocument,
    SourceConnector,
    Question,
    Message,
    MonitoredChannel,
    CustomerAccount,
    User,
    WorkspaceToken,
    WorkspaceSettings,
    SlaPolicy,
    CrmConnection,
    ClassificationFeedback,
    AuditLog,
)


async def create_workspace_deletion_job(
    workspace_id: uuid.UUID,
    actor_slack_user_id: str | None = None,
) -> WorkspaceDeletionJob:
    async with get_session() as session:
        job = WorkspaceDeletionJob(
            workspace_id=workspace_id,
            status="pending",
            actor_slack_user_id=actor_slack_user_id,
        )
        session.add(job)
        await session.flush()
        return job


async def _delete_workspace_data(workspace_id: uuid.UUID, job_id: uuid.UUID) -> None:
    async with get_session(workspace_id) as session:
        job_result = await session.execute(
            select(WorkspaceDeletionJob).where(WorkspaceDeletionJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job is None:
            job = WorkspaceDeletionJob(id=job_id, workspace_id=workspace_id, status="pending")
            session.add(job)
            await session.flush()

        job.status = "running"
        job.started_at = datetime.now(UTC)

        for model in _DELETE_ORDER:
            await session.execute(delete(model).where(model.workspace_id == workspace_id))

        session.add(
            AuditLog(
                workspace_id=workspace_id,
                actor_slack_user_id=job.actor_slack_user_id,
                event_type="workspace_deleted",
                entity_type="workspace",
                entity_id=workspace_id,
            )
        )
        await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        job.status = "complete"
        job.completed_at = datetime.now(UTC)


async def _mark_deletion_failed(job_id: uuid.UUID, error: str) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(WorkspaceDeletionJob).where(WorkspaceDeletionJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is not None:
            job.status = "failed"
            job.error = error[:2000]
            job.completed_at = datetime.now(UTC)


@celery.task(name="relay.delete_workspace_data", bind=True, max_retries=0)
def delete_workspace_data(self, workspace_id: str, job_id: str) -> None:
    wid = uuid.UUID(workspace_id)
    jid = uuid.UUID(job_id)
    try:
        asyncio.run(_delete_workspace_data(wid, jid))
    except Exception as exc:
        asyncio.run(_mark_deletion_failed(jid, type(exc).__name__))
        raise
