"""Async SQLAlchemy session helper with optional RLS workspace context."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.engine import get_session_factory


@asynccontextmanager
async def get_session(workspace_id: UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        if workspace_id is not None:
            await session.execute(
                text("SET LOCAL app.current_workspace_id = :workspace_id"),
                {"workspace_id": str(workspace_id)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

