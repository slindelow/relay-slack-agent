from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from slack_sdk.oauth.installation_store import Installation

from relay.slack.installation_store import DBInstallationStore


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_installation_store_save_creates_workspace_token_and_admin():
    session = AsyncMock()
    workspace = SimpleNamespace(id="W1")

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield session

    installation = Installation(
        team_id="T123",
        team_name="Acme",
        user_id="UINSTALLER",
        bot_token="xoxb-token",
        bot_scopes=["chat:write", "commands"],
    )

    with (
        patch("relay.slack.installation_store.get_session", fake_get_session),
        patch(
            "relay.slack.installation_store.upsert_workspace_from_install",
            new=AsyncMock(return_value=workspace),
        ) as mock_workspace,
        patch("relay.slack.installation_store.store_bot_token", new=AsyncMock()) as mock_token,
        patch("relay.slack.installation_store.bootstrap_first_admin", new=AsyncMock()) as mock_admin,
    ):
        await DBInstallationStore().async_save(installation)

    mock_workspace.assert_awaited_once_with(session, "T123", "Acme")
    mock_token.assert_awaited_once_with(session, "W1", "xoxb-token", "chat:write,commands")
    mock_admin.assert_awaited_once_with(session, "W1", "UINSTALLER")


@pytest.mark.asyncio
async def test_installation_store_find_bot_decrypts_active_token():
    workspace = SimpleNamespace(
        id="W1",
        slack_team_name="Acme",
        installed_at=datetime.now(UTC),
    )
    token_row = SimpleNamespace(
        encrypted_token=b"cipher",
        encrypted_token_nonce=b"nonce",
        scopes="chat:write,commands",
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(workspace), None, _ScalarResult(token_row)])

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield session

    settings = SimpleNamespace(
        kms_provider="none",
        kms_key_id="",
        token_encryption_key_bytes=b"a" * 32,
    )

    with (
        patch("relay.slack.installation_store.get_session", fake_get_session),
        patch("relay.slack.installation_store.get_settings", return_value=settings),
        patch("relay.slack.installation_store.decrypt_token", return_value="xoxb-token") as mock_decrypt,
    ):
        bot = await DBInstallationStore().async_find_bot(
            enterprise_id=None,
            team_id="T123",
            is_enterprise_install=False,
        )

    assert bot is not None
    assert bot.bot_token == "xoxb-token"
    assert bot.team_id == "T123"
    assert bot.team_name == "Acme"
    assert bot.bot_scopes == ["chat:write", "commands"]
    mock_decrypt.assert_called_once_with(b"cipher", b"nonce", b"a" * 32)


@pytest.mark.asyncio
async def test_installation_store_find_bot_returns_none_without_team():
    assert await DBInstallationStore().async_find_bot(enterprise_id=None, team_id=None) is None
