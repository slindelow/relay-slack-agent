"""Plan 2 schema — CRM, accounts, channels, messages, questions, events

Revision ID: 0002_plan2_schema
Revises: 0001_initial_schema
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_plan2_schema"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "crm_connections",
    "customer_accounts",
    "monitored_channels",
    "messages",
    "questions",
    "question_events",
)

RLS_EXPR = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"


def upgrade() -> None:
    # Create PostgreSQL enum types before tables that use them
    crm_provider_enum = postgresql.ENUM("hubspot", "salesforce", name="crm_provider", create_type=False)
    crm_provider_enum.create(op.get_bind(), checkfirst=True)

    question_state_enum = postgresql.ENUM(
        "detected", "open", "claimed", "resolved", "expired",
        name="question_state",
        create_type=False,
    )
    question_state_enum.create(op.get_bind(), checkfirst=True)

    question_urgency_enum = postgresql.ENUM(
        "critical", "high", "normal", "low",
        name="question_urgency",
        create_type=False,
    )
    question_urgency_enum.create(op.get_bind(), checkfirst=True)

    # 1. crm_connections (FK → workspaces)
    op.create_table(
        "crm_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_provider", sa.Enum("hubspot", "salesforce", name="crm_provider"), nullable=False),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_access_token_nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=True),
        sa.Column("encrypted_refresh_token_nonce", sa.LargeBinary(length=12), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "crm_provider", name="uq_crm_connection_provider"),
    )

    # 2. customer_accounts (FK → workspaces, users, sla_policies)
    op.create_table(
        "customer_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("crm_provider", sa.Enum("hubspot", "salesforce", name="crm_provider"), nullable=True),
        sa.Column("external_crm_id", sa.String(length=128), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backup_owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=True),
        sa.Column("sla_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lifecycle_stage", sa.String(length=64), nullable=True),
        sa.Column("arr", sa.Float(), nullable=True),
        sa.Column("renewal_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("external_crm_url", sa.String(length=512), nullable=True),
        sa.Column("manual_tier_override", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["backup_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sla_policy_id"], ["sla_policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "external_crm_id", "crm_provider", name="uq_account_crm"),
    )

    # 3. monitored_channels (FK → workspaces, customer_accounts, users)
    op.create_table(
        "monitored_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_channel_id", sa.String(length=32), nullable=False),
        sa.Column("customer_slack_team_id", sa.String(length=32), nullable=True),
        sa.Column("is_ext_shared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("registered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["customer_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slack_channel_id", name="uq_channel_workspace"),
    )

    # 4. messages (FK → workspaces, monitored_channels)
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_message_ts", sa.String(length=32), nullable=False),
        sa.Column("sender_slack_user_id", sa.String(length=32), nullable=True),
        sa.Column("sender_slack_team_id", sa.String(length=32), nullable=True),
        sa.Column("is_customer_message", sa.Boolean(), nullable=True),
        sa.Column("raw_excerpt", sa.Text(), nullable=True),
        sa.Column("classification_label", sa.Boolean(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classification_variant", sa.String(length=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["monitored_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "channel_id", "slack_message_ts", name="uq_message_ts"),
    )

    # 5. questions (FK → workspaces, monitored_channels, messages, customer_accounts)
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            sa.Enum("detected", "open", "claimed", "resolved", "expired", name="question_state"),
            nullable=False,
            server_default="detected",
        ),
        sa.Column(
            "urgency",
            sa.Enum("critical", "high", "normal", "low", name="question_urgency"),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("title_excerpt", sa.String(length=255), nullable=True),
        sa.Column("next_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["monitored_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["customer_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('detected', 'open', 'claimed', 'resolved', 'expired')",
            name="ck_questions_state",
        ),
        sa.CheckConstraint(
            "urgency IN ('low', 'normal', 'high', 'critical')",
            name="ck_questions_urgency",
        ),
    )

    # 6. question_events (FK → workspaces, questions, users)
    op.create_table(
        "question_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Enable RLS + FORCE RLS + workspace isolation policy on all 6 new tenant tables
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY workspace_isolation ON {table}
            USING (
                workspace_id = {RLS_EXPR}
            )
            """
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS workspace_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("question_events")
    op.drop_table("questions")
    op.drop_table("messages")
    op.drop_table("monitored_channels")
    op.drop_table("customer_accounts")
    op.drop_table("crm_connections")

    # Drop PostgreSQL enum types
    op.execute("DROP TYPE IF EXISTS question_urgency")
    op.execute("DROP TYPE IF EXISTS question_state")
    op.execute("DROP TYPE IF EXISTS crm_provider")
