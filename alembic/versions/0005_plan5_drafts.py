"""Plan 5 schema — drafts, feedback signals, impact metrics

Revision ID: 0005_plan5_drafts
Revises: 0004_plan4_connectors
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_plan5_drafts"
down_revision: str | None = "0004_plan4_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_EXPR = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"

TENANT_TABLES = ("drafts", "feedback_signals", "impact_metrics")


def upgrade() -> None:
    # per-account context card
    op.add_column(
        "customer_accounts",
        sa.Column("account_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("customer_draft", sa.Text(), nullable=True),
        sa.Column("internal_brief", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("editor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_draft_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "editor_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_draft_editor_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "approved_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_draft_approver_same_workspace",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','discarded','sent')",
            name="ck_drafts_status",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_draft_workspace_id"),
    )
    op.create_index("idx_drafts_workspace_question", "drafts", ["workspace_id", "question_id"])
    op.create_index("idx_drafts_workspace_status", "drafts", ["workspace_id", "status"])

    op.create_foreign_key(
        "fk_retrieval_log_draft_same_workspace",
        "retrieval_logs",
        "drafts",
        ["workspace_id", "draft_id"],
        ["workspace_id", "id"],
    )

    op.create_table(
        "feedback_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correction_action", sa.String(64), nullable=False),
        sa.Column("original_label", sa.Boolean(), nullable=True),
        sa.Column("corrected_label", sa.Boolean(), nullable=True),
        sa.Column("original_confidence", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            name="fk_feedback_message_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            name="fk_feedback_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_feedback_draft_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_feedback_actor_same_workspace",
        ),
        sa.CheckConstraint(
            "correction_action IN ('mark_not_question','mark_question','discard_draft','regenerate_draft','incorrect_source','incorrect_response')",
            name="ck_feedback_signals_action",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_feedback_signal_workspace_id"),
    )
    op.create_index("idx_feedback_signals_workspace_question", "feedback_signals", ["workspace_id", "question_id"])

    op.create_table(
        "impact_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("time_to_first_alert_seconds", sa.Integer(), nullable=True),
        sa.Column("time_to_first_draft_seconds", sa.Integer(), nullable=True),
        sa.Column("time_to_send_seconds", sa.Integer(), nullable=True),
        sa.Column("sla_met", sa.Boolean(), nullable=True),
        sa.Column("draft_accepted", sa.Boolean(), nullable=False),
        sa.Column("draft_edit_distance", sa.Integer(), nullable=True),
        sa.Column("alert_to_action", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "account_id"],
            ["customer_accounts.workspace_id", "customer_accounts.id"],
            name="fk_impact_metric_account_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_impact_metric_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_impact_metric_draft_same_workspace",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_impact_metric_workspace_id"),
    )
    op.create_index("idx_impact_metrics_workspace_question", "impact_metrics", ["workspace_id", "question_id"])

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

    op.drop_index("idx_impact_metrics_workspace_question", table_name="impact_metrics")
    op.drop_table("impact_metrics")
    op.drop_index("idx_feedback_signals_workspace_question", table_name="feedback_signals")
    op.drop_table("feedback_signals")
    op.drop_constraint("fk_retrieval_log_draft_same_workspace", "retrieval_logs", type_="foreignkey")
    op.drop_index("idx_drafts_workspace_status", table_name="drafts")
    op.drop_index("idx_drafts_workspace_question", table_name="drafts")
    op.drop_table("drafts")
    op.drop_column("customer_accounts", "account_context")
