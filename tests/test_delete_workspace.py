"""Tests for workspace deletion flow (Plan 7 US-002)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_confirm_modal_structure():
    from relay.commands.delete import _CONFIRM_MODAL

    assert _CONFIRM_MODAL["callback_id"] == "relay_confirm_delete_workspace"
    assert _CONFIRM_MODAL["type"] == "modal"
    # Submit button text must mention destructive action
    submit_text = _CONFIRM_MODAL["submit"]["text"].lower()
    assert "delete" in submit_text


@pytest.mark.asyncio
async def test_handle_delete_workspace_opens_modal():
    from relay.commands.delete import handle_delete_workspace

    ack = AsyncMock()
    client = AsyncMock()
    respond = AsyncMock()
    command = {"trigger_id": "test-trigger-123"}

    await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    ack.assert_called_once()
    client.views_open.assert_called_once()
    call_kwargs = client.views_open.call_args.kwargs
    assert call_kwargs["trigger_id"] == "test-trigger-123"


@pytest.mark.asyncio
async def test_handle_delete_workspace_no_trigger_responds_ephemeral():
    from relay.commands.delete import handle_delete_workspace

    ack = AsyncMock()
    client = AsyncMock()
    respond = AsyncMock()
    command = {}  # no trigger_id

    await handle_delete_workspace(ack=ack, client=client, command=command, respond=respond)

    ack.assert_called_once()
    client.views_open.assert_not_called()
    respond.assert_called_once()
