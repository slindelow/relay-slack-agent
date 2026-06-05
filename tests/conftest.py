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
from sqlalchemy.pool import NullPool

from relay.config import get_settings
from relay.db.models import Base

TENANT_TABLES = (
    "workspace_tokens",
    "workspace_settings",
    "sla_policies",
    "users",
    "crm_connections",
    "customer_accounts",
    "monitored_channels",
    "messages",
    "questions",
    "question_events",
    "classification_feedback",
    "audit_log",
)
TEST_APP_ROLE = "relay_app_test"

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


@pytest_asyncio.fixture
async def engine():
    """Create test engine, apply schema + RLS policies for one test, drop after.

    Function scope avoids pytest-asyncio event-loop reuse issues with asyncpg in CI.
    """
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://relay:relay@localhost:5432/relay_test",
    )
    eng = create_async_engine(url, echo=False, poolclass=NullPool)

    try:
        async with eng.connect() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL test database not reachable — skipping integration tests")

    async with eng.begin() as conn:
        await conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{TEST_APP_ROLE}') THEN
                        CREATE ROLE {TEST_APP_ROLE};
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {TEST_APP_ROLE}"))
        for table in TENANT_TABLES:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            await conn.execute(
                text(
                    f"CREATE POLICY workspace_isolation ON {table} "
                    f"USING (workspace_id = {_RLS_EXPRESSION})"
                )
            )
            await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {TEST_APP_ROLE}"))
        await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON workspaces TO {TEST_APP_ROLE}"))

    yield eng

    async with eng.begin() as conn:
        for table in reversed(TENANT_TABLES):
            await conn.execute(text(f"DROP POLICY IF EXISTS workspace_isolation ON {table}"))
            await conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        await conn.run_sync(Base.metadata.drop_all)

    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Async session for integration tests."""
    session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        await session.execute(text(f"SET ROLE {TEST_APP_ROLE}"))
        yield session
    finally:
        await session.rollback()
        await session.execute(text("RESET ROLE"))
        await session.close()
