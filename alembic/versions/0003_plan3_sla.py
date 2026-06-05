"""Plan 3 schema — SLA engine: alerts, assignments, snoozes

Revision ID: 0003_plan3_sla
Revises: 0002_plan2_schema
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_plan3_sla"
down_revision: str | None = "0002_plan2_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "alerts",
    "assignments",
    "snoozes",
)

RLS_EXPR = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # alerts
    # ------------------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False, server_default="primary"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "id", name="uq_alert_workspace_id"),
        sa.CheckConstraint(
            "alert_type IN ('primary','backup','escalation')",
            name="ck_alerts_alert_type",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_alert_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "recipient_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_alert_recipient_same_workspace",
        ),
    )
    op.create_index("idx_alerts_question_sent", "alerts", ["question_id", "sent_at"])

    # ------------------------------------------------------------------
    # assignments
    # ------------------------------------------------------------------
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "id", name="uq_assignment_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_assignment_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assignee_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_assignment_assignee_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assigned_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_assignment_assigned_by_same_workspace",
        ),
    )
    # Partial index: active assignments (not yet unassigned)
    op.create_index(
        "idx_assignments_question_active",
        "assignments",
        ["question_id"],
        postgresql_where=sa.text("unassigned_at IS NULL"),
    )

    # ------------------------------------------------------------------
    # snoozes
    # ------------------------------------------------------------------
    op.create_table(
        "snoozes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snoozed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_snooze_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_snooze_question_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "snoozed_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_snooze_user_same_workspace",
        ),
    )
    op.create_index("idx_snoozes_question_active", "snoozes", ["question_id", "snoozed_until"])

    # ------------------------------------------------------------------
    # RLS + FORCE RLS on all three tables
    # ------------------------------------------------------------------
    conn = op.get_bind()
    for table in TENANT_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY workspace_isolation ON {table} "
            f"USING (workspace_id = {RLS_EXPR})"
        ))


def downgrade() -> None:
    conn = op.get_bind()
    for table in TENANT_TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS workspace_isolation ON {table}"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("idx_snoozes_question_active", "snoozes")
    op.drop_table("snoozes")

    op.drop_index("idx_assignments_question_active", "assignments")
    op.drop_table("assignments")

    op.drop_index("idx_alerts_question_sent", "alerts")
    op.drop_table("alerts")
