"""Plan 6 schema — knowledge entries, resolution memory

Revision ID: 0006_plan6_memory
Revises: 0005_plan5_drafts
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_plan6_memory"
down_revision: str | None = "0005_plan5_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_EXPR = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"

TENANT_TABLES = ("knowledge_entries",)


def upgrade() -> None:
    op.create_table(
        "knowledge_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("customer_question", sa.Text(), nullable=False),
        sa.Column("internal_answer", sa.Text(), nullable=False),
        sa.Column(
            "source_bundle",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reuse_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="SET NULL",
            name="fk_knowledge_entry_question",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_knowledge_entry_workspace_id"),
    )
    op.create_index(
        "idx_knowledge_entries_workspace_created",
        "knowledge_entries",
        ["workspace_id", "created_at"],
    )

    # Add FK from knowledge_chunks.knowledge_entry_id → knowledge_entries.id
    # (column already exists from migration 0004, just adding the constraint)
    op.create_foreign_key(
        "fk_knowledge_chunk_entry_same_workspace",
        "knowledge_chunks",
        "knowledge_entries",
        ["workspace_id", "knowledge_entry_id"],
        ["workspace_id", "id"],
        ondelete="SET NULL",
    )

    # Add missing recency indexes on tables created in 0005
    op.create_index(
        "idx_impact_metrics_workspace_created",
        "impact_metrics",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "idx_feedback_signals_workspace_created_action",
        "feedback_signals",
        ["workspace_id", "created_at", "correction_action"],
    )

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

    op.drop_index("idx_feedback_signals_workspace_created_action", table_name="feedback_signals")
    op.drop_index("idx_impact_metrics_workspace_created", table_name="impact_metrics")
    op.drop_constraint("fk_knowledge_chunk_entry_same_workspace", "knowledge_chunks", type_="foreignkey")
    op.drop_index("idx_knowledge_entries_workspace_created", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
