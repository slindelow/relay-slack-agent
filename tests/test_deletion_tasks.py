from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

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

from relay.worker.deletion_tasks import _DELETE_ORDER, _delete_workspace_data, create_workspace_deletion_job


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_delete_order_removes_chunks_before_sources_and_workspace_last():
    names = [model.__tablename__ for model in _DELETE_ORDER]
    assert names.index("knowledge_chunks") < names.index("source_documents")
    assert names.index("source_documents") < names.index("source_connectors")
    assert names.index("questions") < names.index("messages")
    assert "workspaces" not in names


@pytest.mark.asyncio
async def test_create_workspace_deletion_job_records_pending_job():
    workspace_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("relay.worker.deletion_tasks.get_session", return_value=_SessionContext(session)):
        job = await create_workspace_deletion_job(workspace_id, actor_slack_user_id="U123")

    assert job.workspace_id == workspace_id
    assert job.status == "pending"
    assert job.actor_slack_user_id == "U123"
    session.add.assert_called_once_with(job)


async def _count(session, model, workspace_id):
    result = await session.execute(
        select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_delete_workspace_data_removes_full_data_tree(engine, monkeypatch):
    import relay.db.engine as engine_module

    monkeypatch.setattr(engine_module, "_engine", engine)
    monkeypatch.setattr(engine_module, "_session_factory", None)

    now = datetime.now(UTC)
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    sla_id = uuid.uuid4()
    account_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    message_id = uuid.uuid4()
    question_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    connector_id = uuid.uuid4()
    document_id = uuid.uuid4()
    knowledge_entry_id = uuid.uuid4()
    job_id = uuid.uuid4()

    async with get_session() as session:
        session.add(
            Workspace(
                id=workspace_id,
                slack_team_id="TDELETE",
                slack_team_name="Delete Test",
            )
        )

    async with get_session(workspace_id) as session:
        session.add_all(
            [
                WorkspaceSettings(workspace_id=workspace_id),
                SlaPolicy(
                    id=sla_id,
                    workspace_id=workspace_id,
                    tier_name="enterprise",
                    response_window_minutes=60,
                    escalation_window_minutes=120,
                ),
                User(
                    id=user_id,
                    workspace_id=workspace_id,
                    slack_user_id="UDELETE",
                    display_name="Delete User",
                    relay_role="admin",
                ),
                WorkspaceToken(
                    workspace_id=workspace_id,
                    token_type="bot",
                    encrypted_token=b"token",
                    encrypted_token_nonce=b"1" * 12,
                ),
                CrmConnection(
                    workspace_id=workspace_id,
                    crm_provider="hubspot",
                    encrypted_access_token=b"access",
                    encrypted_access_token_nonce=b"2" * 12,
                    scopes="crm.objects.companies.read",
                ),
                SourceConnector(
                    id=connector_id,
                    workspace_id=workspace_id,
                    connector_type="github",
                    config={},
                    encrypted_credentials=b"creds",
                    encrypted_credentials_nonce=b"3" * 12,
                ),
            ]
        )
        await session.flush()
        session.add(
            CustomerAccount(
                id=account_id,
                workspace_id=workspace_id,
                name="Delete Account",
                owner_user_id=user_id,
                tier="enterprise",
                sla_policy_id=sla_id,
            )
        )
        await session.flush()
        session.add(
            MonitoredChannel(
                id=channel_id,
                workspace_id=workspace_id,
                account_id=account_id,
                slack_channel_id="CDELETE",
                is_ext_shared=True,
                registered_by_user_id=user_id,
            )
        )
        await session.flush()
        session.add(
            Message(
                id=message_id,
                workspace_id=workspace_id,
                channel_id=channel_id,
                slack_message_ts="1717700000.000001",
                sender_slack_user_id="UDELETE",
                is_customer_message=True,
                raw_excerpt="Can you delete this workspace?",
            )
        )
        await session.flush()
        session.add(
            Question(
                id=question_id,
                workspace_id=workspace_id,
                channel_id=channel_id,
                message_id=message_id,
                account_id=account_id,
                state="open",
                urgency="high",
                title_excerpt="Delete workspace?",
                next_alert_at=now,
            )
        )
        await session.flush()
        session.add_all(
            [
                QuestionEvent(
                    workspace_id=workspace_id,
                    question_id=question_id,
                    event_type="opened",
                    actor_user_id=user_id,
                ),
                Alert(
                    workspace_id=workspace_id,
                    question_id=question_id,
                    recipient_user_id=user_id,
                    alert_type="primary",
                ),
                Assignment(
                    workspace_id=workspace_id,
                    question_id=question_id,
                    assignee_user_id=user_id,
                    assigned_by_user_id=user_id,
                ),
                Snooze(
                    workspace_id=workspace_id,
                    question_id=question_id,
                    snoozed_by_user_id=user_id,
                    snoozed_until=now + timedelta(hours=1),
                ),
            ]
        )
        session.add(
            Draft(
                id=draft_id,
                workspace_id=workspace_id,
                question_id=question_id,
                evidence_bundle={},
                customer_draft="A draft",
                internal_brief="Internal brief",
                status="pending",
                editor_user_id=user_id,
            )
        )
        await session.flush()
        session.add(
            SourceDocument(
                id=document_id,
                workspace_id=workspace_id,
                connector_id=connector_id,
                external_id="doc-1",
                title="Doc 1",
                config={},
                content_hash="doc-hash",
            )
        )
        await session.flush()
        session.add(
            KnowledgeEntry(
                id=knowledge_entry_id,
                workspace_id=workspace_id,
                question_id=question_id,
                title="Memory",
                summary="A memory",
                customer_question="Can you delete this workspace?",
                internal_answer="Yes.",
                source_bundle={},
            )
        )
        await session.flush()
        session.add_all(
            [
                KnowledgeChunk(
                    workspace_id=workspace_id,
                    source_document_id=document_id,
                    chunk_index=0,
                    content="Connector chunk",
                    embedding=[0.0] * 1024,
                    embedding_model="test",
                    embedding_dims=1024,
                    content_hash="connector-chunk",
                ),
                KnowledgeChunk(
                    workspace_id=workspace_id,
                    knowledge_entry_id=knowledge_entry_id,
                    chunk_index=0,
                    content="Memory chunk",
                    embedding=[0.0] * 1024,
                    embedding_model="test",
                    embedding_dims=1024,
                    content_hash="memory-chunk",
                ),
                RetrievalLog(
                    workspace_id=workspace_id,
                    draft_id=draft_id,
                    sources_used=[],
                    query="delete workspace",
                ),
                FeedbackSignal(
                    workspace_id=workspace_id,
                    message_id=message_id,
                    question_id=question_id,
                    draft_id=draft_id,
                    actor_user_id=user_id,
                    correction_action="regenerate_draft",
                ),
                ImpactMetric(
                    workspace_id=workspace_id,
                    account_id=account_id,
                    question_id=question_id,
                    draft_id=draft_id,
                    draft_accepted=False,
                ),
                ClassificationFeedback(
                    workspace_id=workspace_id,
                    message_text="Can you delete this workspace?",
                    slack_message_ts="1717700000.000001",
                    slack_channel_id="CDELETE",
                    corrected_label=True,
                    corrected_by_slack_user_id="UDELETE",
                    correction_action="mark_question",
                ),
                WorkspaceDeletionJob(
                    id=job_id,
                    workspace_id=workspace_id,
                    status="pending",
                    actor_slack_user_id="UDELETE",
                ),
            ]
        )

    await _delete_workspace_data(workspace_id, job_id)

    async with get_session(workspace_id) as session:
        for model in _DELETE_ORDER:
            if model is AuditLog:
                continue
            assert await _count(session, model, workspace_id) == 0
        audit_count = await _count(session, AuditLog, workspace_id)
        assert audit_count == 1

    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        job = await session.get(WorkspaceDeletionJob, job_id)
        assert workspace is None
        assert job is not None
        assert job.status == "complete"


def test_cascade_order_includes_audit_log():
    """audit_log must appear in the cascade deletion order."""
    assert "audit_log" in [model.__tablename__ for model in _DELETE_ORDER]
    # Must come after users so user references are deleted before audit rows
    names = [model.__tablename__ for model in _DELETE_ORDER]
    assert names.index("audit_log") > names.index("users")


def test_poller_uses_is_revoked_flag():
    """Regression: SLA poller must filter on is_revoked=False, not revoked_at IS NULL."""
    import inspect
    import relay.sla.poller as poller_module
    source = inspect.getsource(poller_module)
    assert "is_revoked.is_(False)" in source, "Poller must use is_revoked flag"
    assert "revoked_at.is_(None)" not in source, "Poller must not use revoked_at for revocation check"
