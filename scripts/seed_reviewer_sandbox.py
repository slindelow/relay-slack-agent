#!/usr/bin/env python3
"""Seed the reviewer sandbox with demo data for Slack Marketplace review.

Usage:
    python scripts/seed_reviewer_sandbox.py [--database-url URL]

Re-running is idempotent: the sandbox workspace is found by name and reset.
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from relay.db.models import (
    CustomerAccount,
    Draft,
    DraftStatus,
    KnowledgeEntry,
    Message,
    MonitoredChannel,
    Question,
    QuestionState,
    QuestionUrgency,
    SlaPolicy,
    Snooze,
    User,
    Workspace,
    WorkspaceSettings,
)

SANDBOX_TEAM_ID = "T_RELAY_DEMO"
SANDBOX_TEAM_NAME = "RELAY Reviewer Sandbox"


def _sync_engine(database_url: str):
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    return create_engine(sync_url, echo=False)


def _reset_sandbox(session: Session, workspace_id: uuid.UUID) -> None:
    """Delete all tenant data for the sandbox workspace (cascade order)."""
    tables = [
        "knowledge_chunks", "knowledge_entries",
        "source_documents", "source_connectors",
        "retrieval_logs", "drafts",
        "impact_metrics", "feedback_signals",
        "alerts", "snoozes", "assignments",
        "question_events", "questions", "messages",
        "monitored_channels", "customer_accounts",
        "users", "workspace_tokens", "workspace_settings",
        "sla_policies",
    ]
    for table in tables:
        session.execute(text(f"DELETE FROM {table} WHERE workspace_id = :wid"), {"wid": workspace_id})


def seed(database_url: str) -> None:
    engine = _sync_engine(database_url)
    with Session(engine) as session:
        # Find or create the sandbox workspace
        workspace = session.query(Workspace).filter_by(slack_team_id=SANDBOX_TEAM_ID).first()
        if workspace is None:
            workspace = Workspace(
                id=uuid.uuid4(),
                slack_team_id=SANDBOX_TEAM_ID,
                slack_team_name=SANDBOX_TEAM_NAME,
            )
            session.add(workspace)
            session.flush()
        else:
            _reset_sandbox(session, workspace.id)
            session.flush()

        workspace_id = workspace.id

        # Workspace settings
        session.add(WorkspaceSettings(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            classifier_variant="a",
        ))

        # SLA policies
        sla_enterprise = SlaPolicy(
            id=uuid.uuid4(), workspace_id=workspace_id,
            tier_name="enterprise", response_window_minutes=60, escalation_window_minutes=30,
        )
        sla_starter = SlaPolicy(
            id=uuid.uuid4(), workspace_id=workspace_id,
            tier_name="starter", response_window_minutes=240, escalation_window_minutes=120,
        )
        session.add_all([sla_enterprise, sla_starter])
        session.flush()

        # Demo CSM user
        csm = User(
            id=uuid.uuid4(), workspace_id=workspace_id,
            slack_user_id="U_CSM_DEMO", display_name="Demo CSM",
            email="demo.csm@relay.app", relay_role="admin",
        )
        session.add(csm)
        session.flush()

        # Customer accounts
        acct_enterprise = CustomerAccount(
            id=uuid.uuid4(), workspace_id=workspace_id,
            name="Acme Corp", tier="enterprise",
            arr=180000, renewal_date=(datetime.now(UTC) + timedelta(days=45)).date(),
            owner_user_id=csm.id, sla_policy_id=sla_enterprise.id,
        )
        acct_starter = CustomerAccount(
            id=uuid.uuid4(), workspace_id=workspace_id,
            name="Beta Inc", tier="starter",
            arr=12000, renewal_date=(datetime.now(UTC) + timedelta(days=120)).date(),
            owner_user_id=csm.id, sla_policy_id=sla_starter.id,
        )
        session.add_all([acct_enterprise, acct_starter])
        session.flush()

        # Monitored channels
        ch_acme = MonitoredChannel(
            id=uuid.uuid4(), workspace_id=workspace_id,
            account_id=acct_enterprise.id,
            slack_channel_id="C_ACME_DEMO",
            slack_channel_name="acme-corp-support",
            is_ext_shared=True, is_active=True,
            registered_by_user_id=csm.id,
        )
        ch_beta = MonitoredChannel(
            id=uuid.uuid4(), workspace_id=workspace_id,
            account_id=acct_starter.id,
            slack_channel_id="C_BETA_DEMO",
            slack_channel_name="beta-inc-support",
            is_ext_shared=True, is_active=True,
            registered_by_user_id=csm.id,
        )
        session.add_all([ch_acme, ch_beta])
        session.flush()

        # --- Questions ---

        # 1. Past-SLA question (open, overdue)
        msg_overdue = Message(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_acme.id,
            slack_message_ts="1700000001.000100",
            raw_excerpt="Can you export our audit logs to CSV? We need this for compliance by end of week.",
            is_customer_message=True,
            sender_slack_user_id="U_CUSTOMER_1",
            sender_slack_team_id="T_ACME_EXTERNAL",
        )
        session.add(msg_overdue)
        session.flush()

        q_overdue = Question(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_acme.id,
            message_id=msg_overdue.id,
            account_id=acct_enterprise.id,
            title_excerpt="Can you export our audit logs to CSV?",
            state=QuestionState.open,
            urgency=QuestionUrgency.critical,
            next_alert_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        session.add(q_overdue)

        # 2. Snoozed question
        msg_snoozed = Message(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_acme.id,
            slack_message_ts="1700000002.000200",
            raw_excerpt="Is there a way to set up SSO with our identity provider?",
            is_customer_message=True,
            sender_slack_user_id="U_CUSTOMER_2",
            sender_slack_team_id="T_ACME_EXTERNAL",
        )
        session.add(msg_snoozed)
        session.flush()

        q_snoozed = Question(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_acme.id,
            message_id=msg_snoozed.id,
            account_id=acct_enterprise.id,
            title_excerpt="Is there a way to set up SSO?",
            state=QuestionState.open,
            urgency=QuestionUrgency.high,
            next_alert_at=datetime.now(UTC) + timedelta(hours=4),
        )
        session.add(q_snoozed)
        session.flush()

        snooze = Snooze(
            id=uuid.uuid4(), workspace_id=workspace_id,
            question_id=q_snoozed.id,
            snoozed_by_user_id=csm.id,
            snoozed_until=datetime.now(UTC) + timedelta(hours=4),
        )
        session.add(snooze)

        # 3. Claimed question with a pending draft
        msg_claimed = Message(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_beta.id,
            slack_message_ts="1700000003.000300",
            raw_excerpt="Hi — our API calls are failing with a 429 rate limit error even though we're under our plan limit.",
            is_customer_message=True,
            sender_slack_user_id="U_CUSTOMER_3",
            sender_slack_team_id="T_BETA_EXTERNAL",
        )
        session.add(msg_claimed)
        session.flush()

        q_claimed = Question(
            id=uuid.uuid4(), workspace_id=workspace_id,
            channel_id=ch_beta.id,
            message_id=msg_claimed.id,
            account_id=acct_starter.id,
            title_excerpt="API calls failing with 429 rate limit error",
            state=QuestionState.claimed,
            urgency=QuestionUrgency.normal,
            next_alert_at=datetime.now(UTC) + timedelta(hours=2),
            claimed_at=datetime.now(UTC) - timedelta(minutes=15),
        )
        session.add(q_claimed)
        session.flush()

        draft = Draft(
            id=uuid.uuid4(), workspace_id=workspace_id,
            question_id=q_claimed.id,
            status=DraftStatus.pending,
            customer_draft=(
                "Hi! Thanks for flagging this. The 429 errors are triggered when requests "
                "exceed the per-minute burst limit, even if daily quota is within bounds. "
                "Our docs cover how to implement exponential backoff — I'll share the link now."
            ),
            internal_brief="Rate limiting is per-minute, not per-day. Customer needs backoff docs.",
            confidence=0.87,
            evidence_bundle={},
        )
        session.add(draft)

        # 4 & 5. Resolved questions with knowledge entries
        resolved_pairs = [
            (acct_enterprise, ch_acme, "What are the data retention settings for message history?",
             "Acme Corp — data retention settings for message history", "1700000010.001000"),
            (acct_starter, ch_beta, "Can we get a sandbox environment for testing?",
             "Beta Inc — sandbox environment for testing", "1700000011.001100"),
        ]
        for i, (account, channel, question_text, ke_title, ts) in enumerate(resolved_pairs):
            msg = Message(
                id=uuid.uuid4(), workspace_id=workspace_id,
                channel_id=channel.id,
                slack_message_ts=ts,
                raw_excerpt=question_text,
                is_customer_message=True,
                sender_slack_user_id=f"U_CUSTOMER_R{i}",
                sender_slack_team_id=f"T_CUST_{i}",
            )
            session.add(msg)
            session.flush()

            q_resolved = Question(
                id=uuid.uuid4(), workspace_id=workspace_id,
                channel_id=channel.id,
                message_id=msg.id,
                account_id=account.id,
                title_excerpt=question_text[:80],
                state=QuestionState.resolved,
                urgency=QuestionUrgency.normal,
                resolved_at=datetime.now(UTC) - timedelta(days=1),
            )
            session.add(q_resolved)
            session.flush()

            ke = KnowledgeEntry(
                id=uuid.uuid4(), workspace_id=workspace_id,
                question_id=q_resolved.id,
                title=ke_title,
                summary=f"Resolved question about: {question_text[:60]}",
                customer_question=question_text,
                internal_answer="See product documentation for full details.",
                reuse_count=0,
            )
            session.add(ke)

        session.commit()
        print(f"Sandbox seeded successfully. Workspace ID: {workspace_id}")
        print(f"  Team ID: {SANDBOX_TEAM_ID}")
        print("  Accounts: Acme Corp (Enterprise), Beta Inc (Starter)")
        print("  Questions: 3 open (1 overdue, 1 snoozed, 1 claimed+drafted), 2 resolved")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RELAY reviewer sandbox")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()

    if not args.database_url:
        print("Error: --database-url or DATABASE_URL env var required", file=sys.stderr)
        sys.exit(1)

    seed(args.database_url)


if __name__ == "__main__":
    main()
