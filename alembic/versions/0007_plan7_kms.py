"""Plan 7 — KMS envelope encryption + workspace deletion jobs

Revision ID: 0007_plan7_kms
Revises: 0006_plan6_memory
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_plan7_kms"
down_revision: str | None = "0006_plan6_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # US-001: per-workspace KMS envelope encryption columns
    op.add_column("workspaces", sa.Column("wrapped_dek", sa.LargeBinary(), nullable=True))
    op.add_column("workspaces", sa.Column("kms_key_id", sa.String(256), nullable=True))

    # US-004: GDPR erasure support — soft-delete flag on users
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # US-002: workspace deletion job tracking (system table — no RLS)
    op.create_table(
        "workspace_deletion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_workspace_deletion_jobs_workspace",
        "workspace_deletion_jobs",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
    op.drop_index("idx_workspace_deletion_jobs_workspace", table_name="workspace_deletion_jobs")
    op.drop_table("workspace_deletion_jobs")
    op.drop_column("workspaces", "kms_key_id")
    op.drop_column("workspaces", "wrapped_dek")
