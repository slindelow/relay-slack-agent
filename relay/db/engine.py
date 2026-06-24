import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from relay.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # The Celery worker runs each task in a fresh event loop via asyncio.run().
        # A pooled async connection is bound to the loop that created it, so reusing
        # it from a later task's loop raises "attached to a different loop" /
        # "Event loop is closed". NullPool opens a fresh connection per checkout and
        # closes it on release, which is correct (if less pooled) under that model.
        # The web service runs in a single long-lived loop, so it keeps the pool.
        if os.environ.get("SERVICE_TYPE") == "worker":
            _engine = create_async_engine(
                settings.database_url,
                echo=settings.environment == "development",
                poolclass=NullPool,
            )
        else:
            _engine = create_async_engine(
                settings.database_url,
                echo=settings.environment == "development",
                pool_pre_ping=True,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# Module-level alias — create_async_engine is lazy; no connections open until first query.
async_engine = get_engine()
