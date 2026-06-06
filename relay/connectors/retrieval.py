"""Tenant-safe semantic retrieval for RELAY.

Always scopes vector search to a single workspace to prevent cross-tenant
data leakage. Writes a retrieval_log row on every call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.connectors.embeddings import _get_embeddings
from relay.db.models import KnowledgeEntry, RetrievalLog


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    source_document_id: uuid.UUID | None
    knowledge_entry_id: uuid.UUID | None
    content: str
    embedding_model: str
    embedding_dims: int
    citation: dict = field(default_factory=dict)


async def retrieve(
    workspace_id: uuid.UUID,
    query: str,
    session: AsyncSession,
    top_k: int = 5,
    draft_id: uuid.UUID | None = None,
) -> list[RetrievedChunk]:
    """Return the top-k most relevant KnowledgeChunks for query, scoped to workspace_id.

    Always writes a retrieval_log row. Workspace isolation is enforced both by
    the WHERE clause and by RLS (app.current_workspace_id must be set before call).
    """
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if not query.strip():
        raise ValueError("query must not be empty")

    # Embed the query
    query_vectors = await _get_embeddings([query])
    query_vec = query_vectors[0]

    # pgvector cosine distance: <=>
    # Parameterise the vector as a cast to avoid dialect serialisation issues
    sql = text(
        """
        SELECT id, source_document_id, knowledge_entry_id, content, embedding_model, embedding_dims
        FROM knowledge_chunks
        WHERE workspace_id = :wid
        ORDER BY
            embedding <=> CAST(:qvec AS vector),
            CASE WHEN knowledge_entry_id IS NOT NULL THEN 0 ELSE 1 END
        LIMIT :k
        """
    )
    result = await session.execute(
        sql,
        {
            "wid": str(workspace_id),
            "qvec": f"[{','.join(str(v) for v in query_vec)}]",
            "k": top_k,
        },
    )
    rows = result.fetchall()

    entry_ids = {row.knowledge_entry_id for row in rows if row.knowledge_entry_id is not None}
    entries_by_id: dict[uuid.UUID, KnowledgeEntry] = {}
    if entry_ids:
        entry_result = await session.execute(
            select(KnowledgeEntry).where(
                KnowledgeEntry.workspace_id == workspace_id,
                KnowledgeEntry.id.in_(entry_ids),
            )
        )
        entries_by_id = {entry.id: entry for entry in entry_result.scalars().all()}

    chunks: list[RetrievedChunk] = []
    source_ids: list[str] = []

    for row in rows:
        citation = {}
        if row.knowledge_entry_id is not None:
            entry = entries_by_id.get(row.knowledge_entry_id)
            if entry is not None:
                entry.reuse_count += 1
                citation = {
                    "provider": "relay_memory",
                    "title": entry.title,
                    "url": None,
                    "updated_at": entry.created_at.isoformat() if entry.created_at else None,
                    "stale": False,
                    "summary": entry.summary,
                }

        chunk = RetrievedChunk(
            chunk_id=row.id,
            source_document_id=row.source_document_id,
            knowledge_entry_id=row.knowledge_entry_id,
            content=row.content,
            embedding_model=row.embedding_model,
            embedding_dims=row.embedding_dims,
            citation=citation,
        )
        chunks.append(chunk)
        source_ids.append(str(row.id))

    # Write retrieval log
    log = RetrievalLog(
        workspace_id=workspace_id,
        draft_id=draft_id,
        sources_used=[{"chunk_id": cid} for cid in source_ids],
        query=query,
    )
    session.add(log)

    return chunks
