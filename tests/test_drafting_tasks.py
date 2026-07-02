"""Tests for post-generation CSM notifications in the draft-generation worker task.

Covers the fix for two production bugs (2026-07-02):
- `handle_generate_draft` crashed on Slack's App Home block actions because
  `respond()` requires a response_url that Home tab interactions never carry.
- The worker never told the CSM anything once generation finished (or failed),
  so a slow or crashed run looked indistinguishable from a hung app.

Regression guard: a prior attempt at worker notifications (commit 7cf92c6) was
reverted because it reused `relay.slack.app.app.client`, which is bound to the
web process's event loop and raises "Event loop is closed" inside Celery's
per-task asyncio.run(). These tests patch `slack_sdk.web.async_client.AsyncWebClient`
directly to confirm the fix builds a fresh client instead of touching `app.client`.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _session_cm(execute_results):
    """Build an async-context-manager mock whose session.execute() yields
    `scalar_one_or_none() -> result` for each item in execute_results, in order."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=r))
            for r in execute_results
        ]
    )
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_generate_draft_success_refreshes_home_and_dms_csm():
    from relay.worker.drafting_tasks import _generate_draft_async
    from relay.db.models import QuestionState

    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()

    question = MagicMock(state=QuestionState.claimed.value)
    workspace = MagicMock(slack_team_id="T123")

    get_session_mock = MagicMock(
        side_effect=[
            _session_cm([question]),  # unscoped Question lookup
            _session_cm([workspace]),  # Workspace + bot token lookup
        ]
    )

    mock_slack_client = AsyncMock()

    with (
        patch("relay.db.session.get_session", get_session_mock),
        patch("relay.context.mcp_server.draft_generation_tool", AsyncMock()) as gen_tool,
        patch("relay.slack.oauth.get_bot_token", AsyncMock(return_value="xoxb-fake")),
        patch("slack_sdk.web.async_client.AsyncWebClient", return_value=mock_slack_client) as client_cls,
        patch("relay.slack.home.render_and_publish_home", AsyncMock()) as render_home,
    ):
        await _generate_draft_async(workspace_id, question_id, notify_slack_user_id="U123")

    gen_tool.assert_awaited_once()
    # Fresh client, not the Bolt app.client singleton (see module docstring).
    # (assert_any_call — importing relay.slack.app as part of test collection
    # triggers unrelated AsyncWebClient construction we don't control here.)
    client_cls.assert_any_call(token="xoxb-fake")
    render_home.assert_awaited_once_with(mock_slack_client, "T123", "U123")
    mock_slack_client.chat_postMessage.assert_awaited_once()
    assert "ready" in mock_slack_client.chat_postMessage.call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_generate_draft_failure_notifies_csm_and_reraises():
    from relay.worker.drafting_tasks import _generate_draft_async
    from relay.db.models import QuestionState

    workspace_id = uuid.uuid4()
    question_id = uuid.uuid4()

    question = MagicMock(state=QuestionState.claimed.value)
    workspace = MagicMock(slack_team_id="T123")

    get_session_mock = MagicMock(
        side_effect=[
            _session_cm([question]),
            _session_cm([workspace]),
        ]
    )

    mock_slack_client = AsyncMock()
    boom = RuntimeError("anthropic API down")

    with (
        patch("relay.db.session.get_session", get_session_mock),
        patch("relay.context.mcp_server.draft_generation_tool", AsyncMock(side_effect=boom)),
        patch("relay.slack.oauth.get_bot_token", AsyncMock(return_value="xoxb-fake")),
        patch("slack_sdk.web.async_client.AsyncWebClient", return_value=mock_slack_client),
        pytest.raises(RuntimeError),
    ):
        await _generate_draft_async(workspace_id, question_id, notify_slack_user_id="U123")

    mock_slack_client.chat_postMessage.assert_awaited_once()
    text = mock_slack_client.chat_postMessage.call_args.kwargs["text"].lower()
    assert "failed" in text
