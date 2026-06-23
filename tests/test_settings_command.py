from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text

from relay.commands.settings import (
    SettingsStatus,
    _parse_multiline_csv,
    _upsert_source_connector,
    build_settings_blocks,
    handle_setup_github_connector,
    handle_settings,
    handle_sync_connector,
)
from relay.config import get_settings
from relay.crypto import decrypt_token
from relay.db.models import SourceConnector
from relay.slack.oauth import upsert_workspace_from_install


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _ScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.values)


def test_build_settings_blocks_shows_setup_state():
    blocks = build_settings_blocks(
        SettingsStatus(
            installed=True,
            admin_count=1,
            channel_count=0,
            crm_connected=True,
            source_count=0,
            app_base_url="https://relay.example.com",
        )
    )

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "Slack app installed" in text
    assert "Customer Slack Connect channel registered" in text
    assert "Connect HubSpot" in str(blocks)


def test_build_settings_blocks_mentions_bootstrap_admin():
    blocks = build_settings_blocks(
        SettingsStatus(
            installed=True,
            admin_count=1,
            bootstrapped_admin=True,
            app_base_url="https://relay.example.com",
        )
    )

    assert "first RELAY admin" in str(blocks)


def test_build_settings_blocks_shows_connector_sync_actions():
    connector = SimpleNamespace(
        id=uuid.uuid4(),
        connector_type="github",
        sync_status="synced",
        last_synced_at=None,
    )
    blocks = build_settings_blocks(
        SettingsStatus(
            installed=True,
            admin_count=1,
            app_base_url="https://relay.example.com",
            connector_rows=[connector],
        )
    )

    assert "Connected sources" in str(blocks)
    assert "relay_sync_connector" in str(blocks)


def test_parse_multiline_csv_accepts_commas_and_lines():
    assert _parse_multiline_csv("owner/a, owner/b\nowner/c\n\n") == [
        "owner/a",
        "owner/b",
        "owner/c",
    ]


@pytest.mark.asyncio
async def test_handle_settings_returns_blocks(monkeypatch):
    workspace_id = uuid.uuid4()
    workspace_session = AsyncMock()
    workspace_session.execute = AsyncMock(return_value=_ScalarResult(SimpleNamespace(id=workspace_id)))

    scoped_session = AsyncMock()
    scoped_session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(1),
            _ScalarResult(2),
            _ScalarResult(1),
            _ScalarResult(3),
            _ScalarsResult([]),
            _ScalarResult(None),
        ]
    )

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield scoped_session if workspace_id else workspace_session

    settings = SimpleNamespace(app_base_url="https://relay.example.com")

    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch("relay.commands.settings.get_session", fake_get_session),
        patch("relay.commands.settings.get_settings", return_value=settings),
    ):
        await handle_settings(
            ack=ack,
            respond=respond,
            command={"team_id": "T123", "user_id": "U_ADMIN"},
        )

    ack.assert_awaited_once()
    kwargs = respond.await_args.kwargs
    assert kwargs["response_type"] == "ephemeral"
    assert "blocks" in kwargs


@pytest.mark.asyncio
async def test_handle_settings_bootstraps_first_admin(monkeypatch):
    workspace_id = uuid.uuid4()
    workspace_session = AsyncMock()
    workspace_session.execute = AsyncMock(return_value=_ScalarResult(SimpleNamespace(id=workspace_id)))

    scoped_session = AsyncMock()
    scoped_session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(0),
            _ScalarResult(None),
            _ScalarResult(0),
            _ScalarResult(0),
            _ScalarResult(0),
            _ScalarsResult([]),
            _ScalarResult(None),
        ]
    )
    scoped_session.add = MagicMock()
    scoped_session.flush = AsyncMock()

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield scoped_session if workspace_id else workspace_session

    settings = SimpleNamespace(app_base_url="https://relay.example.com")
    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch("relay.commands.settings.get_session", fake_get_session),
        patch("relay.commands.settings.get_settings", return_value=settings),
    ):
        await handle_settings(
            ack=ack,
            respond=respond,
            command={"team_id": "T123", "user_id": "U_BOOT"},
        )

    scoped_session.add.assert_called_once()
    scoped_session.flush.assert_awaited_once()
    assert "first RELAY admin" in str(respond.await_args.kwargs["blocks"])


@pytest.mark.asyncio
async def test_handle_settings_workspace_missing():
    workspace_session = AsyncMock()
    workspace_session.execute = AsyncMock(return_value=_ScalarResult(None))

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield workspace_session

    ack = AsyncMock()
    respond = AsyncMock()

    with patch("relay.commands.settings.get_session", fake_get_session):
        await handle_settings(ack=ack, respond=respond, command={"team_id": "T123"})

    respond.assert_awaited_once_with(
        response_type="ephemeral",
        text="RELAY is not installed for this workspace yet.",
    )


@pytest.mark.asyncio
async def test_upsert_source_connector_encrypts_credentials(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_CONNECTOR", "Connector Corp")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )

    connector = await _upsert_source_connector(
        db_session,
        workspace_id=workspace.id,
        connector_type="github",
        credentials="ghp-secret",
        config={"repo_list": ["owner/repo"], "markdown_paths": ["README.md"]},
    )
    await db_session.flush()

    assert connector.encrypted_credentials != b"ghp-secret"
    assert connector.config["repo_list"] == ["owner/repo"]
    assert (
        decrypt_token(
            connector.encrypted_credentials,
            connector.encrypted_credentials_nonce,
            get_settings().token_encryption_key_bytes,
        )
        == "ghp-secret"
    )


@pytest.mark.asyncio
async def test_upsert_source_connector_updates_existing_connector(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_CONNECTOR_UPDATE", "Connector Corp")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )

    first = await _upsert_source_connector(
        db_session,
        workspace_id=workspace.id,
        connector_type="github",
        credentials="first",
        config={"repo_list": ["owner/old"], "markdown_paths": []},
    )
    await db_session.flush()
    first_id = first.id

    second = await _upsert_source_connector(
        db_session,
        workspace_id=workspace.id,
        connector_type="github",
        credentials="second",
        config={"repo_list": ["owner/new"], "markdown_paths": []},
    )
    await db_session.flush()

    result = await db_session.execute(
        select(SourceConnector).where(
            SourceConnector.workspace_id == workspace.id,
            SourceConnector.connector_type == "github",
        )
    )
    rows = list(result.scalars())
    assert len(rows) == 1
    assert second.id == first_id
    assert rows[0].config["repo_list"] == ["owner/new"]


@pytest.mark.asyncio
async def test_setup_github_connector_rejects_non_admin():
    ack = AsyncMock()
    client = AsyncMock()
    workspace = SimpleNamespace(id=uuid.uuid4())

    with (
        patch("relay.commands.settings._workspace_for_team", new=AsyncMock(return_value=workspace)),
        patch("relay.commands.settings._is_admin", new=AsyncMock(return_value=False)),
    ):
        await handle_setup_github_connector(
            ack=ack,
            body={"team": {"id": "T123"}, "user": {"id": "U_VIEWER"}, "trigger_id": "trig"},
            client=client,
        )

    ack.assert_awaited_once()
    client.views_open.assert_not_called()


@pytest.mark.asyncio
async def test_sync_connector_action_enqueues_worker():
    ack = AsyncMock()
    respond = AsyncMock()
    workspace = SimpleNamespace(id=uuid.uuid4())
    connector_id = uuid.uuid4()

    with (
        patch("relay.commands.settings._workspace_for_team", new=AsyncMock(return_value=workspace)),
        patch("relay.commands.settings._is_admin", new=AsyncMock(return_value=True)),
        patch("relay.worker.connector_tasks.sync_connector.delay") as mock_delay,
    ):
        await handle_sync_connector(
            ack=ack,
            body={
                "team": {"id": "T123"},
                "user": {"id": "U_ADMIN"},
                "actions": [{"value": str(connector_id)}],
            },
            respond=respond,
        )

    mock_delay.assert_called_once_with(str(workspace.id), str(connector_id))
    respond.assert_awaited_once_with(response_type="ephemeral", text="Source sync started.")


@pytest.mark.asyncio
async def test_handle_disconnect_slack_search_revokes_token_and_responds():
    """Disconnect handler revokes the user's token and confirms via respond."""
    from relay.commands.settings import handle_disconnect_slack_search

    body = {
        "team": {"id": "T_DISCO"},
        "user": {"id": "U_DISCO"},
    }
    ack = AsyncMock()
    respond = AsyncMock()

    workspace_mock = SimpleNamespace(id=uuid.uuid4())

    # First context manager (cross-tenant): returns workspace
    session_ctx_cross = AsyncMock()
    session_ctx_cross.__aenter__ = AsyncMock(return_value=session_ctx_cross)
    session_ctx_cross.__aexit__ = AsyncMock(return_value=False)
    session_ctx_cross.execute = AsyncMock(
        return_value=_ScalarResult(workspace_mock)
    )

    # Second context manager (tenant-scoped): just needs to work
    session_ctx_scoped = AsyncMock()
    session_ctx_scoped.__aenter__ = AsyncMock(return_value=session_ctx_scoped)
    session_ctx_scoped.__aexit__ = AsyncMock(return_value=False)

    def _get_session_side_effect(workspace_id=None):
        return session_ctx_cross if workspace_id is None else session_ctx_scoped

    with (
        patch("relay.commands.settings.get_session", side_effect=_get_session_side_effect),
        patch("relay.commands.settings.revoke_user_search_tokens") as mock_revoke,
    ):
        await handle_disconnect_slack_search(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    mock_revoke.assert_awaited_once_with(
        session_ctx_scoped,
        workspace_id=workspace_mock.id,
        slack_user_id="U_DISCO",
    )
    respond.assert_awaited_once()
    call_text = respond.await_args.kwargs.get("text") or ""
    assert "disconnected" in call_text.lower()
