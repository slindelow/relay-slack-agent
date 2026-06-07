"""Plan 7 schema — workspace deletion job tracking

Revision ID: 0007_plan7_deletion
Revises: 0006_plan6_memory
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_plan7_deletion"
down_revision: str | None = "0006_plan6_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_deletion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("actor_slack_user_id", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','complete','failed')",
            name="ck_workspace_deletion_jobs_status",
        ),
    )
    op.create_index(
        "idx_workspace_deletion_jobs_workspace_created",
        "workspace_deletion_jobs",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_workspace_deletion_jobs_workspace_created", table_name="workspace_deletion_jobs")
    op.drop_table("workspace_deletion_jobs")
