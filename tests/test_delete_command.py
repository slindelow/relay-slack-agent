from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from relay.commands.delete import build_delete_workspace_modal, handle_delete_workspace_data


def test_build_delete_workspace_modal_warns_irreversible():
    modal = build_delete_workspace_modal("T123", "U123")
    text = "\n".join(block.get("text", {}).get("text", "") for block in modal["blocks"])
    assert modal["callback_id"] == "relay_confirm_delete_workspace_data"
    assert "permanently delete" in text
    assert "cannot be undone" in text


@pytest.mark.asyncio
async def test_handle_delete_workspace_data_opens_modal():
    ack = AsyncMock()
    client = AsyncMock()
    command = {"team_id": "T123", "user_id": "U123", "trigger_id": "trigger"}

    await handle_delete_workspace_data(ack, command, client)

    ack.assert_awaited_once()
    client.views_open.assert_awaited_once()
    assert client.views_open.await_args.kwargs["trigger_id"] == "trigger"
