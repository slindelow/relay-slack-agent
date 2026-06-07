from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from relay.slack.events import handle_message


@pytest.mark.asyncio
async def test_message_event_enqueues_minimal_payload():
    event = {
        "team": "T123",
        "channel": "C123",
        "ts": "123.456",
        "user": "U123",
        "text": "hello" * 200,
    }

    with patch("relay.worker.tasks.process_slack_event") as task:
        await handle_message(event, say=None, logger=MagicMock())

    payload = task.delay.call_args.args[0]
    assert payload["team_id"] == "T123"
    assert payload["channel_id"] == "C123"
    assert len(payload["text"]) == 500
