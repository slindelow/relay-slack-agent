import importlib
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from relay.commands import register as register_module
from relay.commands.register import _fetch_channel_metadata, _parse_register_args, handle_register
from relay.db.models import CustomerAccount, MonitoredChannel, User
from relay.slack.oauth import upsert_workspace_from_install


def _blocks_text(blocks):
    parts = []
    for block in blocks:
        if "text" in block:
            parts.append(block["text"].get("text", ""))
        parts.extend(field.get("text", "") for field in block.get("fields", []))
    return "\n".join(parts)


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
    blocks = respond.call_args.kwargs["blocks"]
    text = _blocks_text(blocks)
    assert "RELAY command center" in text
    assert "main message box" in text
    assert "not a thread reply" in text
    assert "Set up RELAY" in text
    assert "/relay setup" in text
    assert "Add a customer channel" in text
    assert "/relay add #channel Account Name enterprise @owner" in text
    assert "Ask knowledge" in text
    assert "Check account pulse" in text
    assert "Admin/privacy" in text


@pytest.mark.asyncio
async def test_unknown_subcommand_returns_error_text(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    await help_handler(ack=ack, respond=respond, command={"text": "bogus", "user_id": "U123"})
    assert "bogus" in respond.call_args.kwargs["text"]
    assert "/relay help" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_unknown_subcommand_suggests_close_match(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    await help_handler(ack=ack, respond=respond, command={"text": "setings", "user_id": "U123"})
    assert "Did you mean `/relay settings`" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["settings", "setup", "sources", "connect"])
async def test_setup_aliases_route_to_settings(help_handler, alias):
    ack = AsyncMock()
    respond = AsyncMock()
    settings = AsyncMock()

    with patch("relay.commands.help.handle_settings", settings):
        await help_handler(
            ack=ack,
            respond=respond,
            command={"text": alias, "user_id": "U123", "team_id": "T123"},
        )

    settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_alias_routes_to_register(help_handler):
    ack = AsyncMock()
    respond = AsyncMock()
    register = AsyncMock()

    with patch("relay.commands.help.handle_register", register):
        await help_handler(
            ack=ack,
            respond=respond,
            command={
                "text": "add <#C123456|acme-corp> Acme Corp enterprise",
                "user_id": "U123",
                "team_id": "T123",
            },
            client=AsyncMock(),
        )

    register.assert_awaited_once()
    assert register.await_args.kwargs["command"]["text"].startswith("add ")


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
    assert "/relay add #channel Account Name enterprise @owner" in respond.call_args.kwargs["text"]
    assert "Valid tiers" in respond.call_args.kwargs["text"]


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
    assert "Valid tiers" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_register_valid_shows_success():
    """Valid input with channel mention registers the channel and returns success."""
    ack = AsyncMock()
    respond = AsyncMock()
    workspace_id = uuid.uuid4()
    account_id = uuid.uuid4()
    registering_user_id = uuid.uuid4()

    workspace_session = AsyncMock()
    workspace_result = SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=workspace_id))
    workspace_session.execute = AsyncMock(return_value=workspace_result)

    write_session = AsyncMock()

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield write_session if workspace_id else workspace_session

    async def fake_get_or_create_user(session, workspace_id, slack_user_id):
        return SimpleNamespace(id=registering_user_id)

    async def fake_get_or_create_account(session, workspace_id, account_name, tier, owner_user_id):
        return SimpleNamespace(id=account_id)

    async def fake_register_channel(**kwargs):
        return SimpleNamespace(
            slack_channel_name=None,
            customer_slack_team_id=None,
            is_ext_shared=False,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(register_module, "get_session", fake_get_session)
    monkeypatch.setattr(register_module, "_get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(register_module, "_get_or_create_account", fake_get_or_create_account)
    monkeypatch.setattr(register_module, "register_channel", fake_register_channel)
    monkeypatch.setattr(register_module, "_fetch_channel_metadata", AsyncMock(return_value=("T_CUSTOMER", True)))
    with patch("relay.auth.require_relay_admin", new=AsyncMock(return_value=True)):
        await handle_register(
            ack=ack,
            respond=respond,
            command={
                "text": "register <#C123456|acme-corp> Acme Corp enterprise",
                "user_id": "U123",
                "team_id": "T_INTERNAL",
            },
        )
    monkeypatch.undo()
    ack.assert_called_once()
    response_text = respond.call_args.kwargs["text"]
    assert "acme-corp" in response_text
    assert "Acme Corp" in response_text
    assert "enterprise" in response_text


def test_parse_register_args_extracts_owner():
    parsed = _parse_register_args("register <#C123456|acme-corp> Acme Corp enterprise <@UOWNER>")
    assert parsed == ("C123456", "acme-corp", "Acme Corp", "enterprise", "UOWNER")


def test_parse_register_args_accepts_add_alias():
    parsed = _parse_register_args("add <#C123456|acme-corp> Acme Corp enterprise <@UOWNER>")
    assert parsed == ("C123456", "acme-corp", "Acme Corp", "enterprise", "UOWNER")


def test_parse_register_args_accepts_channel_mention_without_name():
    # Slack omits the |channel-name suffix in some escaped slash-command payloads.
    parsed = _parse_register_args("register <#C123456> Acme Corp enterprise")
    assert parsed == ("C123456", "C123456", "Acme Corp", "enterprise", None)


@pytest.mark.asyncio
async def test_fetch_channel_metadata_extracts_external_team():
    client = AsyncMock()
    client.conversations_info = AsyncMock(
        return_value={
            "channel": {
                "is_ext_shared": True,
                "shared_team_ids": ["T_INTERNAL", "T_CUSTOMER"],
            }
        }
    )

    customer_team_id, is_ext_shared = await _fetch_channel_metadata(client, "C123456", "T_INTERNAL")

    assert customer_team_id == "T_CUSTOMER"
    assert is_ext_shared is True


@pytest.mark.asyncio
async def test_register_missing_team_id_returns_error():
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
    assert "missing Slack workspace id" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_register_requires_verified_slack_connect_channel(monkeypatch):
    ack = AsyncMock()
    respond = AsyncMock()
    workspace_id = uuid.uuid4()

    workspace_session = AsyncMock()
    workspace_session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=workspace_id))
    )
    auth_session = AsyncMock()

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        yield auth_session if workspace_id else workspace_session

    monkeypatch.setattr(register_module, "get_session", fake_get_session)
    monkeypatch.setattr(register_module, "_fetch_channel_metadata", AsyncMock(return_value=(None, False)))

    with patch("relay.auth.require_relay_admin", new=AsyncMock(return_value=True)):
        await handle_register(
            ack=ack,
            respond=respond,
            client=AsyncMock(),
            command={
                "text": "register <#C123456|acme-corp> Acme Corp enterprise",
                "user_id": "U_ADMIN",
                "team_id": "T_INTERNAL",
            },
        )

    assert "Slack Connect" in respond.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_register_persists_account_and_channel(db_session, monkeypatch):
    workspace = await upsert_workspace_from_install(db_session, "T_REGISTER", "Register Corp")
    db_session.add(
        User(
            workspace_id=workspace.id,
            slack_user_id="UREGISTRAR",
            relay_role="admin",
        )
    )
    await db_session.flush()

    @asynccontextmanager
    async def fake_get_session(workspace_id=None):
        if workspace_id is not None:
            await db_session.execute(
                text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
                {"workspace_id": str(workspace_id)},
            )
        yield db_session

    client = AsyncMock()
    client.conversations_info = AsyncMock(
        return_value={
            "channel": {
                "is_ext_shared": True,
                "shared_team_ids": ["T_REGISTER", "T_CUSTOMER"],
            }
        }
    )
    monkeypatch.setattr(register_module, "get_session", fake_get_session)

    ack = AsyncMock()
    respond = AsyncMock()
    await handle_register(
        ack=ack,
        respond=respond,
        client=client,
        command={
            "text": "register <#C123456|acme-corp> Acme Corp enterprise <@UOWNER>",
            "user_id": "UREGISTRAR",
            "team_id": "T_REGISTER",
        },
    )
    await db_session.flush()

    account = (
        await db_session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace.id,
                CustomerAccount.name == "Acme Corp",
            )
        )
    ).scalar_one()
    channel = (
        await db_session.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.workspace_id == workspace.id,
                MonitoredChannel.slack_channel_id == "C123456",
            )
        )
    ).scalar_one()

    assert account.tier == "enterprise"
    assert channel.account_id == account.id
    assert channel.slack_channel_name == "acme-corp"
    assert channel.customer_slack_team_id == "T_CUSTOMER"
    assert channel.is_ext_shared is True
