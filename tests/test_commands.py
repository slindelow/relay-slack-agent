import importlib
from unittest.mock import AsyncMock

import pytest

from relay.commands.register import handle_register


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


# ---------------------------------------------------------------------------
# /relay register tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_missing_args_shows_usage():
    """No arguments after 'register' → usage message."""
    ack = AsyncMock()
    respond = AsyncMock()
    await handle_register(ack=ack, respond=respond, command={"text": "register", "user_id": "U123"})
    ack.assert_called_once()
    respond.assert_called_once()
    assert "Usage" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_register_invalid_tier_shows_usage():
    """Tier not in (enterprise, pro, starter) → usage message."""
    ack = AsyncMock()
    respond = AsyncMock()
    await handle_register(
        ack=ack,
        respond=respond,
        command={"text": "register #acme-corp Acme Corp gold", "user_id": "U123"},
    )
    ack.assert_called_once()
    assert "Usage" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_register_valid_shows_success():
    """Valid input with channel mention → success message."""
    ack = AsyncMock()
    respond = AsyncMock()
    await handle_register(
        ack=ack,
        respond=respond,
        command={
            "text": "register <#C123456|acme-corp> Acme Corp enterprise",
            "user_id": "U123",
        },
    )
    ack.assert_called_once()
    response_text = respond.call_args.kwargs["text"]
    assert "acme-corp" in response_text
    assert "Acme Corp" in response_text
    assert "enterprise" in response_text

