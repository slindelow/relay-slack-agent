"""Abstract base class for all RELAY source connectors."""

import abc
import uuid


class Connector(abc.ABC):
    """All source connectors implement this interface."""

    @abc.abstractmethod
    async def sync(self, workspace_id: uuid.UUID) -> None:
        """Fetch remote documents, chunk, embed, and upsert into knowledge_chunks."""

    @abc.abstractmethod
    async def search(self, workspace_id: uuid.UUID, query: str, top_k: int) -> list:
        """Return top-k matching chunks for query. Raise NotImplementedError if centralised retrieval is used."""

    @abc.abstractmethod
    def citation(self, chunk) -> dict:
        """Return citation metadata dict for a chunk row."""

    @abc.abstractmethod
    async def disconnect(self, workspace_id: uuid.UUID) -> None:
        """Mark the connector as disconnected (sets disconnected_at)."""

    @abc.abstractmethod
    async def purge(self, workspace_id: uuid.UUID) -> None:
        """Delete all knowledge_chunks and source_documents for this connector."""
