"""Plan 7 schema — workspace KMS envelope encryption

Revision ID: 0008_plan7_kms
Revises: 0007_plan7_deletion
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_plan7_kms"
down_revision: str | None = "0007_plan7_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("wrapped_dek", sa.LargeBinary(), nullable=True))
    op.add_column("workspaces", sa.Column("kms_key_id", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "kms_key_id")
    op.drop_column("workspaces", "wrapped_dek")
