"""Integration tests for relay.slack.oauth.

Requires a live PostgreSQL test database (see tests/conftest.py).
Tests are skipped automatically when the database is not reachable.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from relay.db.models import SlaPolicy, Workspace, WorkspaceSettings, WorkspaceToken
from relay.slack.oauth import store_bot_token, upsert_workspace_from_install


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _count(session, model, workspace_id):
    result = await session.execute(
        select(model).where(model.workspace_id == workspace_id)
    )
    return len(result.scalars().all())


async def _set_workspace_context(session, workspace_id):
    await session.execute(
        text("SET LOCAL app.current_workspace_id = :wid"),
        {"wid": str(workspace_id)},
    )


# ---------------------------------------------------------------------------
# upsert_workspace_from_install
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_install_creates_workspace(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_NEW_001", slack_team_name="Acme Corp"
    )
    await db_session.flush()

    assert workspace.id is not None
    assert workspace.slack_team_id == "T_NEW_001"
    assert workspace.slack_team_name == "Acme Corp"
    assert workspace.uninstalled_at is None


@pytest.mark.asyncio
async def test_new_install_seeds_workspace_settings(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_NEW_002", slack_team_name="Acme Corp"
    )
    await db_session.flush()
    await _set_workspace_context(db_session, workspace.id)

    count = await _count(db_session, WorkspaceSettings, workspace.id)
    assert count == 1


@pytest.mark.asyncio
async def test_new_install_seeds_default_sla_policies(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_NEW_003", slack_team_name="Acme Corp"
    )
    await db_session.flush()
    await _set_workspace_context(db_session, workspace.id)

    result = await db_session.execute(
        select(SlaPolicy)
        .where(SlaPolicy.workspace_id == workspace.id)
        .order_by(SlaPolicy.response_window_minutes)
    )
    policies = result.scalars().all()
    assert len(policies) == 3

    tiers = {p.tier_name: p for p in policies}
    assert tiers["enterprise"].response_window_minutes == 30
    assert tiers["enterprise"].escalation_window_minutes == 45
    assert tiers["pro"].response_window_minutes == 120
    assert tiers["pro"].escalation_window_minutes == 180
    assert tiers["starter"].response_window_minutes == 480
    assert tiers["starter"].escalation_window_minutes == 600


@pytest.mark.asyncio
async def test_reinstall_reuses_workspace(db_session, relay_settings):
    first = await upsert_workspace_from_install(
        db_session, slack_team_id="T_REINST_001", slack_team_name="Acme v1"
    )
    await db_session.flush()
    first_id = first.id

    second = await upsert_workspace_from_install(
        db_session, slack_team_id="T_REINST_001", slack_team_name="Acme v2"
    )
    await db_session.flush()

    assert second.id == first_id
    assert second.slack_team_name == "Acme v2"


@pytest.mark.asyncio
async def test_reinstall_clears_uninstalled_at(db_session, relay_settings):
    from datetime import datetime, timezone

    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_REINST_002", slack_team_name="Acme"
    )
    await db_session.flush()
    workspace.uninstalled_at = datetime.now(timezone.utc)
    await db_session.flush()

    reinstalled = await upsert_workspace_from_install(
        db_session, slack_team_id="T_REINST_002", slack_team_name="Acme"
    )
    await db_session.flush()
    assert reinstalled.uninstalled_at is None


# ---------------------------------------------------------------------------
# store_bot_token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_bot_token_encrypts_token(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_TOKEN_001", slack_team_name="Acme"
    )
    await db_session.flush()

    token = await store_bot_token(
        db_session, workspace.id, bot_token="xoxb-test-token", scopes="chat:write"
    )
    await db_session.flush()

    assert token.encrypted_token != b"xoxb-test-token"
    assert len(token.encrypted_token_nonce) == 12
    assert token.token_type == "bot"
    assert token.is_revoked is False


@pytest.mark.asyncio
async def test_store_bot_token_revokes_previous(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_TOKEN_002", slack_team_name="Acme"
    )
    await db_session.flush()
    await _set_workspace_context(db_session, workspace.id)

    first = await store_bot_token(
        db_session, workspace.id, bot_token="xoxb-first", scopes="chat:write"
    )
    await db_session.flush()
    assert first.is_revoked is False

    await store_bot_token(
        db_session, workspace.id, bot_token="xoxb-second", scopes="chat:write,users:read"
    )
    await db_session.flush()

    await db_session.refresh(first)
    assert first.is_revoked is True
    assert first.revoked_at is not None


@pytest.mark.asyncio
async def test_store_bot_token_stores_scopes(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session, slack_team_id="T_TOKEN_003", slack_team_name="Acme"
    )
    await db_session.flush()

    token = await store_bot_token(
        db_session, workspace.id, bot_token="xoxb-scoped", scopes="chat:write,users:read"
    )
    await db_session.flush()

    assert token.scopes == "chat:write,users:read"
