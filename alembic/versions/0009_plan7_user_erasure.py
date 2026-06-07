"""Plan 7 schema — individual user erasure

Revision ID: 0009_plan7_user_erasure
Revises: 0008_plan7_kms
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_plan7_user_erasure"
down_revision: str | None = "0008_plan7_kms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
