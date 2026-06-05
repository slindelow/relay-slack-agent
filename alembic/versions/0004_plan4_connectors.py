"""Plan 4 schema — source connectors, chunks, retrieval logs

Revision ID: 0004_plan4_connectors
Revises: 0003_plan3_sla
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_plan4_connectors"
down_revision: str | None = "0003_plan3_sla"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "source_connectors",
    "source_documents",
    "knowledge_chunks",
    "retrieval_logs",
)

RLS_EXPR = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "source_connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_type", sa.String(32), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("encrypted_credentials", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_credentials_nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("sync_status", sa.String(32), nullable=False, server_default="not_synced"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("connector_type IN ('google_drive','github','notion')", name="ck_source_connectors_type"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_source_connector_workspace_id"),
    )
    op.create_index(
        "idx_source_connectors_workspace_active",
        "source_connectors",
        ["workspace_id"],
        postgresql_where=sa.text("disconnected_at IS NULL"),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connector_id"],
            ["source_connectors.workspace_id", "source_connectors.id"],
            ondelete="CASCADE",
            name="fk_source_document_connector_same_workspace",
        ),
        sa.UniqueConstraint("workspace_id", "connector_id", "external_id", name="uq_source_document_external_id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_source_document_workspace_id"),
    )
    op.create_index("idx_source_documents_workspace_connector", "source_documents", ["workspace_id", "connector_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("knowledge_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embedding_model", sa.String(64), nullable=False),
        sa.Column("embedding_dims", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("embedding_dims = 1536", name="ck_knowledge_chunks_embedding_dims"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_document_id"],
            ["source_documents.workspace_id", "source_documents.id"],
            ondelete="CASCADE",
            name="fk_knowledge_chunk_source_document_same_workspace",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_knowledge_chunk_workspace_id"),
        sa.UniqueConstraint("workspace_id", "content_hash", name="uq_knowledge_chunk_content_hash"),
    )
    op.create_index("idx_knowledge_chunks_workspace_source", "knowledge_chunks", ["workspace_id", "source_document_id"])
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunks_embedding
        ON knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )

    op.create_table(
        "retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sources_used", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_retrieval_log_workspace_id"),
    )
    op.create_index("idx_retrieval_logs_workspace_retrieved", "retrieval_logs", ["workspace_id", "retrieved_at"])

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

    op.drop_index("idx_retrieval_logs_workspace_retrieved", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")

    op.drop_index("idx_knowledge_chunks_embedding", table_name="knowledge_chunks")
    op.drop_index("idx_knowledge_chunks_workspace_source", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    op.drop_index("idx_source_documents_workspace_connector", table_name="source_documents")
    op.drop_table("source_documents")

    op.drop_index("idx_source_connectors_workspace_active", table_name="source_connectors")
    op.drop_table("source_connectors")
