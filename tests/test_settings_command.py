from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from relay.commands.settings import SettingsStatus, build_settings_blocks, handle_settings


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


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
            command={"team_id": "T123"},
        )

    ack.assert_awaited_once()
    kwargs = respond.await_args.kwargs
    assert kwargs["response_type"] == "ephemeral"
    assert "blocks" in kwargs


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
