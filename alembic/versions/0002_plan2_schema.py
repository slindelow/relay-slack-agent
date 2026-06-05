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
    op.create_table(
        "crm_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_provider", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_access_token_nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=True),
        sa.Column("encrypted_refresh_token_nonce", sa.LargeBinary(length=12), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "crm_provider", name="uq_crm_connection_provider"),
    )
    op.create_table(
        "customer_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("crm_provider", sa.String(length=32), nullable=True),
        sa.Column("external_crm_id", sa.String(length=128), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backup_owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("sla_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lifecycle_stage", sa.String(length=64), nullable=True),
        sa.Column("arr", sa.Numeric(12, 2), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("external_crm_url", sa.Text(), nullable=True),
        sa.Column("manual_tier_override", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["backup_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sla_policy_id"], ["sla_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_customer_accounts_workspace_domain", "customer_accounts", ["workspace_id", "domain"])
    op.create_index(
        "uq_customer_external_crm_id_active",
        "customer_accounts",
        ["workspace_id", "crm_provider", "external_crm_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND external_crm_id IS NOT NULL"),
    )
    op.create_table(
        "monitored_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_channel_id", sa.String(length=32), nullable=False),
        sa.Column("slack_channel_name", sa.String(length=255), nullable=True),
        sa.Column("customer_slack_team_id", sa.String(length=32), nullable=True),
        sa.Column("is_ext_shared", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("registered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["customer_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slack_channel_id", name="uq_monitored_channel_workspace"),
    )
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_message_ts", sa.String(length=32), nullable=False),
        sa.Column("slack_thread_ts", sa.String(length=32), nullable=True),
        sa.Column("sender_slack_user_id", sa.String(length=32), nullable=True),
        sa.Column("sender_slack_team_id", sa.String(length=32), nullable=True),
        sa.Column("is_customer_message", sa.Boolean(), nullable=False),
        sa.Column("raw_excerpt", sa.Text(), nullable=False),
        sa.Column("classification_label", sa.Boolean(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classification_variant", sa.String(length=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["monitored_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "channel_id", "slack_message_ts", name="uq_message_slack_ts"),
    )
    op.create_index("idx_messages_workspace_channel_ts", "messages", ["workspace_id", "channel_id", "slack_message_ts"])
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("next_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_count", sa.Integer(), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("urgency", sa.String(length=32), nullable=False),
        sa.Column("title_excerpt", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('detected', 'open', 'claimed', 'resolved', 'expired')", name="ck_questions_state"),
        sa.CheckConstraint("urgency IN ('low', 'normal', 'high', 'critical')", name="ck_questions_urgency"),
        sa.ForeignKeyConstraint(["account_id"], ["customer_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["monitored_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_questions_workspace_state", "questions", ["workspace_id", "state"])
    op.create_index(
        "idx_questions_sla_check",
        "questions",
        ["next_alert_at", "workspace_id"],
        postgresql_where=sa.text("state IN ('open', 'claimed')"),
    )
    op.create_table(
        "question_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_question_events_question_created", "question_events", ["question_id", "created_at"])

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

    op.drop_index("idx_question_events_question_created", table_name="question_events")
    op.drop_table("question_events")
    op.drop_index("idx_questions_sla_check", table_name="questions")
    op.drop_index("idx_questions_workspace_state", table_name="questions")
    op.drop_table("questions")
    op.drop_index("idx_messages_workspace_channel_ts", table_name="messages")
    op.drop_table("messages")
    op.drop_table("monitored_channels")
    op.drop_index("uq_customer_external_crm_id_active", table_name="customer_accounts")
    op.drop_index("idx_customer_accounts_workspace_domain", table_name="customer_accounts")
    op.drop_table("customer_accounts")
    op.drop_table("crm_connections")
