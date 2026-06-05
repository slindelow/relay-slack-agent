import importlib
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def help_handler(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    module = importlib.import_module("relay.commands.help")
    return module.relay_help


@pytest.mark.asyncio
async def test_relay_help_acks_and_responds(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    await help_handler(ack=ack, respond=respond, command={"text": "", "user_id": "U123"})
    ack.assert_called_once()
    respond.assert_called_once()


@pytest.mark.asyncio
async def test_relay_help_response_contains_blocks(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    await help_handler(ack=ack, respond=respond, command={"text": "help", "user_id": "U123"})
    assert "blocks" in respond.call_args.kwargs


@pytest.mark.asyncio
async def test_unknown_subcommand_returns_error_text(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    await help_handler(ack=ack, respond=respond, command={"text": "bogus", "user_id": "U123"})
    assert "bogus" in respond.call_args.kwargs["text"]

