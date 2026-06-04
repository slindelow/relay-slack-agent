"""Fixtures for database integration tests.

Unit tests (test_config, test_crypto, etc.) do not use these fixtures.
Integration tests (test_oauth, test_rls) require a live PostgreSQL instance.
Tests are skipped automatically when the database is not reachable.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from relay.config import get_settings
from relay.db.models import Base

TENANT_TABLES = (
    "workspace_tokens",
    "workspace_settings",
    "sla_policies",
    "users",
    "classification_feedback",
    "audit_log",
)

_RLS_EXPRESSION = "NULLIF(current_setting('app.current_workspace_id', true), '')::uuid"


@pytest.fixture
def relay_settings(monkeypatch):
    """Inject minimal valid settings and clear the LRU cache before/after."""
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://relay:relay@localhost:5432/relay")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test engine, apply schema + RLS policies once per session, drop after."""
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://relay:relay@localhost:5432/relay_test",
    )
    eng = create_async_engine(url, echo=False)

    try:
        async with eng.connect() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL test database not reachable — skipping integration tests")

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for table in TENANT_TABLES:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(
                text(
                    f"CREATE POLICY workspace_isolation ON {table} "
                    f"USING (workspace_id = {_RLS_EXPRESSION})"
                )
            )

    yield eng

    async with eng.begin() as conn:
        for table in reversed(TENANT_TABLES):
            await conn.execute(text(f"DROP POLICY IF EXISTS workspace_isolation ON {table}"))
            await conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        await conn.run_sync(Base.metadata.drop_all)

    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Async session with automatic rollback after each test."""
    conn = await engine.connect()
    await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await conn.rollback()
        await conn.close()
