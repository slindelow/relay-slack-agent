"""MCP + RTS context foundation

Revision ID: 0010_mcp_rts_context
Revises: 0009_plan7_user_erasure
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_mcp_rts_context"
down_revision: str | None = "0009_plan7_user_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_slack_search_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("slack_user_id", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_access_token_nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["users.workspace_id", "users.id"],
            ondelete="CASCADE",
            name="fk_user_slack_search_token_user_same_workspace",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_user_slack_search_token_workspace_id"),
    )
    op.create_index(
        "uq_user_slack_search_token_active_user",
        "user_slack_search_tokens",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_revoked = false"),
    )

    op.create_table(
        "context_tool_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_slack_user_id", sa.String(length=32), nullable=True),
        sa.Column("tool_name", sa.String(length=96), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=True),
        sa.Column("draft_id", sa.UUID(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_context_tool_log_actor_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_context_tool_log_draft_same_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            name="fk_context_tool_log_question_same_workspace",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_context_tool_log_workspace_id"),
    )
    op.create_index(
        "idx_context_tool_logs_workspace_created",
        "context_tool_logs",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_context_tool_logs_workspace_created", table_name="context_tool_logs")
    op.drop_table("context_tool_logs")
    op.drop_index("uq_user_slack_search_token_active_user", table_name="user_slack_search_tokens")
    op.drop_table("user_slack_search_tokens")
