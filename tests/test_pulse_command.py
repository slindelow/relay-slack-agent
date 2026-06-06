from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from relay.commands.pulse import (
    AccountPulse,
    _detail_blocks,
    _parse_pulse_query,
    _summary_blocks,
    handle_pulse,
)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _account(name="Acme", owner=None, backup=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        tier="enterprise",
        arr=120000,
        renewal_date=date.today(),
        owner=owner,
        backup_owner=backup,
    )


def test_parse_pulse_query_strips_subcommand():
    assert _parse_pulse_query("pulse Acme") == "Acme"
    assert _parse_pulse_query("Acme") == "Acme"


def test_summary_blocks_show_top_accounts():
    owner = SimpleNamespace(display_name="Sam", slack_user_id="U1", is_ooo=False)
    pulse = AccountPulse(account=_account(owner=owner), open_count=3)

    blocks = _summary_blocks([pulse])

    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "Acme" in text
    assert "3 open" in text
    assert "enterprise" in text
    assert "Sam" in text


def test_detail_blocks_show_account_pulse():
    owner = SimpleNamespace(display_name="Priya", slack_user_id="U1", is_ooo=True)
    backup = SimpleNamespace(display_name="Lee", slack_user_id="U2", is_ooo=False)
    pulse = AccountPulse(
        account=_account(owner=owner, backup=backup),
        open_count=2,
        sla_rate="75.0%",
        last_resolved="2026-06-05",
    )

    blocks = _detail_blocks(pulse)

    text = "\n".join(
        block.get("text", {}).get("text", "") + "\n".join(field["text"] for field in block.get("fields", []))
        for block in blocks
    )
    assert "Open questions" in text
    assert "75.0%" in text
    assert "2026-06-05" in text
    assert "backup: Lee" in text


@pytest.mark.asyncio
async def test_handle_pulse_account_not_found():
    workspace_id = uuid.uuid4()
    workspace = SimpleNamespace(id=workspace_id)
    session = AsyncMock()
    ack = AsyncMock()
    respond = AsyncMock()

    with (
        patch("relay.commands.pulse._workspace_for_team", new=AsyncMock(return_value=workspace)),
        patch("relay.commands.pulse.get_session", return_value=_SessionContext(session)),
        patch("relay.commands.pulse._account_detail_pulse", new=AsyncMock(return_value=None)),
    ):
        await handle_pulse(ack, respond, {"text": "pulse MissingCo", "team_id": "T123"})

    respond.assert_awaited_once_with(
        response_type="ephemeral",
        text="Account not found. Run `/relay register` to add it.",
    )


@pytest.mark.asyncio
async def test_handle_pulse_summary_returns_blocks():
    workspace_id = uuid.uuid4()
    workspace = SimpleNamespace(id=workspace_id)
    session = AsyncMock()
    ack = AsyncMock()
    respond = AsyncMock()
    pulse = AccountPulse(account=_account(), open_count=1)

    with (
        patch("relay.commands.pulse._workspace_for_team", new=AsyncMock(return_value=workspace)),
        patch("relay.commands.pulse.get_session", return_value=_SessionContext(session)),
        patch("relay.commands.pulse._top_account_pulses", new=AsyncMock(return_value=[pulse])),
    ):
        await handle_pulse(ack, respond, {"text": "pulse", "team_id": "T123"})

    kwargs = respond.await_args.kwargs
    assert kwargs["response_type"] == "ephemeral"
    assert "blocks" in kwargs
