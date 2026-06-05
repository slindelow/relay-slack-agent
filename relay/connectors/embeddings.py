"""Shared embedding pipeline for RELAY source connectors.

Turns text chunks into vectors and persists them as KnowledgeChunk rows.
Idempotent: chunks with an existing content_hash for the workspace are skipped.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.db.models import KnowledgeChunk

if TYPE_CHECKING:
    pass

_BATCH_SIZE = 20


async def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """Call the configured embedding API and return one vector per text."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "openai":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        result = await client.embeddings.create(
            input=texts,
            model="text-embedding-3-small",
        )
        return [item.embedding for item in result.data]

    # Default: voyage
    import voyageai
    client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    result = await client.embed(texts, model="voyage-3")
    return result.embeddings


async def embed_chunks(
    workspace_id: uuid.UUID,
    chunks: list[str],
    connector_id: uuid.UUID | None,
    source_document_id: uuid.UUID | None,
    session: AsyncSession,
) -> list[uuid.UUID]:
    """Embed text chunks and persist as KnowledgeChunk rows.

    Returns the UUIDs of all persisted chunks (new and pre-existing).
    Skips chunks whose content_hash already exists for this workspace.
    """
    if not chunks:
        return []

    settings = get_settings()
    provider = settings.embedding_provider.lower()
    embedding_model = "voyage-3" if provider != "openai" else "text-embedding-3-small"
    embedding_dims = 1536

    # Compute hashes and determine which need embedding
    hashes = [hashlib.sha256(c.encode()).hexdigest() for c in chunks]

    existing = await session.execute(
        select(KnowledgeChunk.content_hash, KnowledgeChunk.id).where(
            KnowledgeChunk.workspace_id == workspace_id,
            KnowledgeChunk.content_hash.in_(hashes),
        )
    )
    existing_map: dict[str, uuid.UUID] = {row.content_hash: row.id for row in existing}

    new_indices = [i for i, h in enumerate(hashes) if h not in existing_map]

    chunk_ids: list[uuid.UUID] = []
    # Preserve ordering: fill in existing IDs first then patch new ones in below
    id_by_index: dict[int, uuid.UUID] = {
        i: existing_map[hashes[i]] for i in range(len(chunks)) if hashes[i] in existing_map
    }

    # Embed new chunks in batches
    if new_indices:
        new_texts = [chunks[i] for i in new_indices]
        vectors: list[list[float]] = []
        for batch_start in range(0, len(new_texts), _BATCH_SIZE):
            batch = new_texts[batch_start : batch_start + _BATCH_SIZE]
            vectors.extend(await _get_embeddings(batch))

        for pos, idx in enumerate(new_indices):
            row = KnowledgeChunk(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                source_document_id=source_document_id,
                knowledge_entry_id=None,
                chunk_index=idx,
                content=chunks[idx],
                embedding=vectors[pos],
                embedding_model=embedding_model,
                embedding_dims=embedding_dims,
                content_hash=hashes[idx],
            )
            session.add(row)
            await session.flush()
            id_by_index[idx] = row.id

    for i in range(len(chunks)):
        chunk_ids.append(id_by_index[i])

    return chunk_ids
