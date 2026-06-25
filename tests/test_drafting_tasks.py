"""Tests for the draft-ready CSM notification (claim → draft → review flow)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_notify_draft_ready_includes_review_button():
    from relay.worker.drafting_tasks import _notify_draft_ready

    draft_id = uuid.uuid4()
    with patch("relay.slack.app.app") as mock_app:
        mock_app.client.chat_postMessage = AsyncMock()
        await _notify_draft_ready("U123", draft_id, "How do I configure SSO?")

    mock_app.client.chat_postMessage.assert_awaited_once()
    kwargs = mock_app.client.chat_postMessage.call_args.kwargs
    assert kwargs["channel"] == "U123"
    buttons = [
        element
        for block in kwargs["blocks"]
        if block.get("type") == "actions"
        for element in block.get("elements", [])
    ]
    assert any(
        b["action_id"] == "relay_open_draft_modal" and b["value"] == str(draft_id)
        for b in buttons
    ), buttons
