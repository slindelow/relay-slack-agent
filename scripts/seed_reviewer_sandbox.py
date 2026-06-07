"""Seed an idempotent Slack Marketplace reviewer sandbox."""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from relay.db.models import (
    Alert,
    Assignment,
    AuditLog,
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

SANDBOX_TEAM_ID = "T_RELAY_REVIEW"
SANDBOX_TEAM_NAME = "RELAY Reviewer Sandbox"

_RESET_ORDER = (
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
    AuditLog,
    WorkspaceDeletionJob,
)


async def _reset_existing_workspace() -> None:
    async with get_session() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.slack_team_id == SANDBOX_TEAM_ID)
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            return

        for model in _RESET_ORDER:
            await session.execute(delete(model).where(model.workspace_id == workspace.id))
        await session.execute(delete(Workspace).where(Workspace.id == workspace.id))


async def seed_reviewer_sandbox() -> uuid.UUID:
    """Reset and seed the reviewer workspace, returning its workspace UUID."""
    await _reset_existing_workspace()

    now = datetime.now(UTC)
    workspace_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    enterprise_owner_id = uuid.uuid4()
    backup_owner_id = uuid.uuid4()
    starter_owner_id = uuid.uuid4()
    enterprise_account_id = uuid.uuid4()
    starter_account_id = uuid.uuid4()
    enterprise_channel_id = uuid.uuid4()
    starter_channel_id = uuid.uuid4()
    enterprise_sla_id = uuid.uuid4()
    starter_sla_id = uuid.uuid4()

    message_ids = [uuid.uuid4() for _ in range(5)]
    question_ids = [uuid.uuid4() for _ in range(5)]
    draft_id = uuid.uuid4()

    async with get_session() as session:
        session.add(
            Workspace(
                id=workspace_id,
                slack_team_id=SANDBOX_TEAM_ID,
                slack_team_name=SANDBOX_TEAM_NAME,
            )
        )
        session.add(WorkspaceSettings(workspace_id=workspace_id))
        session.add_all(
            [
                SlaPolicy(
                    id=enterprise_sla_id,
                    workspace_id=workspace_id,
                    tier_name="enterprise",
                    response_window_minutes=60,
                    escalation_window_minutes=120,
                ),
                SlaPolicy(
                    id=starter_sla_id,
                    workspace_id=workspace_id,
                    tier_name="starter",
                    response_window_minutes=240,
                    escalation_window_minutes=480,
                ),
            ]
        )
        session.add_all(
            [
                User(
                    id=admin_id,
                    workspace_id=workspace_id,
                    slack_user_id="UREVIEWADMIN",
                    display_name="Riley Reviewer",
                    email="reviewer@example.com",
                    relay_role="admin",
                ),
                User(
                    id=enterprise_owner_id,
                    workspace_id=workspace_id,
                    slack_user_id="UENTOWNER",
                    display_name="Eden Enterprise",
                    email="eden@example.com",
                    relay_role="admin",
                ),
                User(
                    id=backup_owner_id,
                    workspace_id=workspace_id,
                    slack_user_id="UBACKUP",
                    display_name="Blake Backup",
                    email="blake@example.com",
                    relay_role="admin",
                ),
                User(
                    id=starter_owner_id,
                    workspace_id=workspace_id,
                    slack_user_id="USTARTEROWNER",
                    display_name="Sam Starter",
                    email="sam@example.com",
                    relay_role="viewer",
                ),
            ]
        )
        session.add_all(
            [
                CustomerAccount(
                    id=enterprise_account_id,
                    workspace_id=workspace_id,
                    name="Acme Enterprise",
                    domain="acme.example",
                    owner_user_id=enterprise_owner_id,
                    backup_owner_user_id=backup_owner_id,
                    tier="enterprise",
                    sla_policy_id=enterprise_sla_id,
                    lifecycle_stage="customer",
                    arr=125000,
                    renewal_date=(now + timedelta(days=45)).date(),
                    health_score=0.82,
                ),
                CustomerAccount(
                    id=starter_account_id,
                    workspace_id=workspace_id,
                    name="Beta Starter",
                    domain="beta.example",
                    owner_user_id=starter_owner_id,
                    tier="starter",
                    sla_policy_id=starter_sla_id,
                    lifecycle_stage="customer",
                    arr=6000,
                    renewal_date=(now + timedelta(days=140)).date(),
                    health_score=0.91,
                ),
            ]
        )
        session.add_all(
            [
                MonitoredChannel(
                    id=enterprise_channel_id,
                    workspace_id=workspace_id,
                    account_id=enterprise_account_id,
                    slack_channel_id="C_REVIEW_ACME",
                    slack_channel_name="ext-acme-support",
                    customer_slack_team_id="T_ACME_CUSTOMER",
                    is_ext_shared=True,
                    registered_by_user_id=admin_id,
                ),
                MonitoredChannel(
                    id=starter_channel_id,
                    workspace_id=workspace_id,
                    account_id=starter_account_id,
                    slack_channel_id="C_REVIEW_BETA",
                    slack_channel_name="ext-beta-support",
                    customer_slack_team_id="T_BETA_CUSTOMER",
                    is_ext_shared=True,
                    registered_by_user_id=admin_id,
                ),
            ]
        )

        messages = [
            Message(
                id=message_ids[0],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                slack_message_ts="1717700000.000001",
                slack_thread_ts="1717700000.000001",
                sender_slack_user_id="U_ACME_CUSTOMER",
                sender_slack_team_id="T_ACME_CUSTOMER",
                is_customer_message=True,
                raw_excerpt="Can you confirm our SSO certificate rotation steps before Friday?",
                classification_label=True,
                classification_confidence=0.94,
                classification_variant="a",
            ),
            Message(
                id=message_ids[1],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                slack_message_ts="1717700300.000001",
                slack_thread_ts="1717700300.000001",
                sender_slack_user_id="U_ACME_CUSTOMER",
                sender_slack_team_id="T_ACME_CUSTOMER",
                is_customer_message=True,
                raw_excerpt="Is the audit export API available for our security review?",
                classification_label=True,
                classification_confidence=0.89,
                classification_variant="a",
            ),
            Message(
                id=message_ids[2],
                workspace_id=workspace_id,
                channel_id=starter_channel_id,
                slack_message_ts="1717700600.000001",
                slack_thread_ts="1717700600.000001",
                sender_slack_user_id="U_BETA_CUSTOMER",
                sender_slack_team_id="T_BETA_CUSTOMER",
                is_customer_message=True,
                raw_excerpt="Can we add two more teammates to the pilot workspace?",
                classification_label=True,
                classification_confidence=0.86,
                classification_variant="a",
            ),
            Message(
                id=message_ids[3],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                slack_message_ts="1717690000.000001",
                slack_thread_ts="1717690000.000001",
                sender_slack_user_id="U_ACME_CUSTOMER",
                sender_slack_team_id="T_ACME_CUSTOMER",
                is_customer_message=True,
                raw_excerpt="What is the approved wording for our data retention answer?",
                classification_label=True,
                classification_confidence=0.92,
                classification_variant="a",
            ),
            Message(
                id=message_ids[4],
                workspace_id=workspace_id,
                channel_id=starter_channel_id,
                slack_message_ts="1717690300.000001",
                slack_thread_ts="1717690300.000001",
                sender_slack_user_id="U_BETA_CUSTOMER",
                sender_slack_team_id="T_BETA_CUSTOMER",
                is_customer_message=True,
                raw_excerpt="Do you have a checklist for inviting customer guests?",
                classification_label=True,
                classification_confidence=0.88,
                classification_variant="a",
            ),
        ]
        session.add_all(messages)

        questions = [
            Question(
                id=question_ids[0],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                message_id=message_ids[0],
                account_id=enterprise_account_id,
                state="open",
                urgency="critical",
                title_excerpt="SSO certificate rotation steps",
                next_alert_at=now - timedelta(minutes=30),
                last_alert_at=now - timedelta(hours=2),
                alert_count=2,
            ),
            Question(
                id=question_ids[1],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                message_id=message_ids[1],
                account_id=enterprise_account_id,
                state="open",
                urgency="high",
                title_excerpt="Audit export API availability",
                next_alert_at=now + timedelta(hours=4),
                alert_count=1,
            ),
            Question(
                id=question_ids[2],
                workspace_id=workspace_id,
                channel_id=starter_channel_id,
                message_id=message_ids[2],
                account_id=starter_account_id,
                state="claimed",
                urgency="normal",
                title_excerpt="Add teammates to pilot workspace",
                next_alert_at=now + timedelta(hours=2),
                claimed_at=now - timedelta(minutes=10),
            ),
            Question(
                id=question_ids[3],
                workspace_id=workspace_id,
                channel_id=enterprise_channel_id,
                message_id=message_ids[3],
                account_id=enterprise_account_id,
                state="resolved",
                urgency="normal",
                title_excerpt="Data retention wording",
                resolved_at=now - timedelta(days=2),
            ),
            Question(
                id=question_ids[4],
                workspace_id=workspace_id,
                channel_id=starter_channel_id,
                message_id=message_ids[4],
                account_id=starter_account_id,
                state="resolved",
                urgency="low",
                title_excerpt="Customer guest invite checklist",
                resolved_at=now - timedelta(days=5),
            ),
        ]
        session.add_all(questions)
        session.add_all(
            [
                Snooze(
                    workspace_id=workspace_id,
                    question_id=question_ids[1],
                    snoozed_by_user_id=enterprise_owner_id,
                    snoozed_until=now + timedelta(hours=4),
                    reason="Waiting for API team confirmation.",
                ),
                Assignment(
                    workspace_id=workspace_id,
                    question_id=question_ids[2],
                    assignee_user_id=starter_owner_id,
                    assigned_by_user_id=admin_id,
                    assigned_at=now - timedelta(minutes=10),
                ),
                Alert(
                    workspace_id=workspace_id,
                    question_id=question_ids[0],
                    recipient_user_id=enterprise_owner_id,
                    alert_type="primary",
                    sent_at=now - timedelta(hours=2),
                ),
            ]
        )
        session.add(
            Draft(
                id=draft_id,
                workspace_id=workspace_id,
                question_id=question_ids[0],
                evidence_bundle={
                    "sources": [
                        {
                            "title": "SSO certificate rotation runbook",
                            "url": "https://docs.example.com/sso-rotation",
                        }
                    ]
                },
                customer_draft=(
                    "Yes. Rotate the new certificate in your IdP first, upload it in RELAY, "
                    "then verify SAML login in a private browser before removing the old cert."
                ),
                internal_brief="Acme needs SSO rotation guidance before Friday.",
                confidence=0.87,
                status="pending",
                editor_user_id=enterprise_owner_id,
            )
        )
        session.add_all(
            [
                KnowledgeEntry(
                    workspace_id=workspace_id,
                    question_id=question_ids[3],
                    title="Data retention wording",
                    summary="Use the approved 90-day raw excerpt and one-year metadata wording.",
                    customer_question="What is the approved wording for our data retention answer?",
                    internal_answer=(
                        "Raw Slack excerpts are retained for up to 90 days; operational metadata "
                        "and approved response memory are retained for up to one year."
                    ),
                    source_bundle={"sources": ["privacy_policy"]},
                    reuse_count=3,
                ),
                KnowledgeEntry(
                    workspace_id=workspace_id,
                    question_id=question_ids[4],
                    title="Customer guest invite checklist",
                    summary="Starter customers can invite guests after admin approval.",
                    customer_question="Do you have a checklist for inviting customer guests?",
                    internal_answer=(
                        "Confirm the customer domain, invite the guest to the shared channel, "
                        "and ask the workspace admin to approve the Slack Connect invitation."
                    ),
                    source_bundle={"sources": ["onboarding_checklist"]},
                    reuse_count=1,
                ),
            ]
        )
        session.add(
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=admin_id,
                actor_slack_user_id="UREVIEWADMIN",
                event_type="reviewer_sandbox_seeded",
                entity_type="workspace",
                entity_id=workspace_id,
            )
        )

    return workspace_id


def main() -> None:
    workspace_id = asyncio.run(seed_reviewer_sandbox())
    print(f"Seeded {SANDBOX_TEAM_NAME} ({SANDBOX_TEAM_ID}) workspace_id={workspace_id}")


if __name__ == "__main__":
    main()
