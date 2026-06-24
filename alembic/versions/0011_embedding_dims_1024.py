"""Align knowledge_chunks embedding to 1024 dims (voyage-3)

The schema was created with vector(1536) (OpenAI text-embedding-3-small),
but the default embedding provider is voyage-3, which emits 1024-dim vectors.
Inserts failed with "expected 1536 dimensions, not 1024". This retypes the
column and check constraint to 1024 to match the active provider.

Revision ID: 0011_embedding_dims_1024
Revises: 0010_mcp_rts_context
"""

from alembic import op

revision: str = "0011_embedding_dims_1024"
down_revision: str | None = "0010_mcp_rts_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No durable data: every sync failed before any row persisted. Clear any
    # partial rows so the column retype cannot trip on a stale 1536-dim value.
    op.execute("DELETE FROM knowledge_chunks")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_embedding")
    op.drop_constraint("ck_knowledge_chunks_embedding_dims", "knowledge_chunks", type_="check")
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.create_check_constraint(
        "ck_knowledge_chunks_embedding_dims", "knowledge_chunks", "embedding_dims = 1024"
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunks_embedding
        ON knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM knowledge_chunks")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_embedding")
    op.drop_constraint("ck_knowledge_chunks_embedding_dims", "knowledge_chunks", type_="check")
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.create_check_constraint(
        "ck_knowledge_chunks_embedding_dims", "knowledge_chunks", "embedding_dims = 1536"
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_chunks_embedding
        ON knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
