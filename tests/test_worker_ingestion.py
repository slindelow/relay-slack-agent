"""Unit tests for process_slack_event worker."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENV_VARS = {
    "SLACK_CLIENT_ID": "client",
    "SLACK_CLIENT_SECRET": "secret",
    "SLACK_SIGNING_SECRET": "signing",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "TOKEN_ENCRYPTION_KEY": "a" * 64,
    "ANTHROPIC_API_KEY": "sk-test",
    "APP_BASE_URL": "https://relay.example.com",
}


def make_channel(
    workspace_id: uuid.UUID | None = None,
    channel_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    customer_slack_team_id: str | None = "TCUSTOMER",
) -> MagicMock:
    ch = MagicMock()
    ch.workspace_id = workspace_id or uuid.uuid4()
    ch.id = channel_id or uuid.uuid4()
    ch.account_id = account_id or uuid.uuid4()
    ch.customer_slack_team_id = customer_slack_team_id
    return ch


def make_classify_result(confidence: float, is_question: bool = True, variant: str = "a") -> MagicMock:
    result = MagicMock()
    result.confidence = confidence
    result.is_question = is_question
    result.variant = variant
    return result


def make_session_ctx(channel_or_none):
    """Return an async context manager that yields a mock session.

    The session's execute() returns a result whose scalar_one_or_none() returns
    channel_or_none for the first (channel lookup) call.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = channel_or_none
    mock_session.execute.return_value = mock_result

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        yield mock_session

    return _ctx, mock_session


def make_payload(
    team_id: str = "TWORKSPACE",
    channel_id: str = "CCHANNEL",
    ts: str = "123.456",
    user: str = "UUSER",
    sender_team: str = "TCUSTOMER",
    text: str = "How do I do X?",
) -> dict:
    return {
        "team_id": team_id,
        "channel_id": channel_id,
        "ts": ts,
        "user": user,
        "team": sender_team,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_skips_unmonitored_channel(monkeypatch):
    """When DB returns None for MonitoredChannel, no Message is created."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)

    from relay.config import get_settings
    get_settings.cache_clear()

    session_ctx, mock_session = make_session_ctx(None)

    with patch("relay.db.session.get_session", new=session_ctx):
        with patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=True)):
            with patch("classifier.classify.classify_message", new=AsyncMock()) as mock_classify:
                from relay.worker.tasks import _process_slack_event_async
                await _process_slack_event_async(make_payload())

    mock_classify.assert_not_called()
    mock_session.add.assert_not_called()

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_process_event_skips_internal_sender(monkeypatch):
    """When sender_team_id != customer_slack_team_id, no classify call is made."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)

    from relay.config import get_settings
    get_settings.cache_clear()

    channel = make_channel(customer_slack_team_id="TCUSTOMER")
    session_ctx, mock_session = make_session_ctx(channel)

    # Sender is from the internal workspace, not the customer team
    payload = make_payload(sender_team="TINTERNAL")

    with patch("relay.db.session.get_session", new=session_ctx):
        with patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=True)):
            with patch("classifier.classify.classify_message", new=AsyncMock()) as mock_classify:
                from relay.worker.tasks import _process_slack_event_async
                await _process_slack_event_async(payload)

    mock_classify.assert_not_called()
    mock_session.add.assert_not_called()

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_process_event_creates_open_question_above_threshold(monkeypatch):
    """confidence=0.9 >= open_threshold=0.85 → Question with state='open'."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CLASSIFIER_OPEN_THRESHOLD", "0.85")
    monkeypatch.setenv("CLASSIFIER_CANDIDATE_THRESHOLD", "0.60")

    from relay.config import get_settings
    get_settings.cache_clear()

    channel = make_channel(customer_slack_team_id="TCUSTOMER")

    # We need two separate session contexts: one for channel lookup, one for write
    # Use a single context factory that tracks calls
    call_count = [0]
    mock_write_session = AsyncMock()
    mock_write_session.add = MagicMock()
    mock_write_session.flush = AsyncMock()

    mock_read_result = MagicMock()
    mock_read_result.scalar_one_or_none.return_value = channel
    mock_read_session = AsyncMock()
    mock_read_session.add = MagicMock()
    mock_read_session.flush = AsyncMock()
    mock_read_session.execute.return_value = mock_read_result

    @asynccontextmanager
    async def _session_ctx(workspace_id=None):
        call_count[0] += 1
        if workspace_id is None:
            yield mock_read_session
        else:
            yield mock_write_session

    classify_result = make_classify_result(confidence=0.9)

    with patch("relay.db.session.get_session", new=_session_ctx):
        with patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=True)):
            with patch("classifier.classify.classify_message", new=AsyncMock(return_value=classify_result)):
                from relay.worker.tasks import _process_slack_event_async
                await _process_slack_event_async(make_payload())

    # Check that session.add was called with a Question having state="open"
    from relay.db.models import Question
    added_objects = [call.args[0] for call in mock_write_session.add.call_args_list]
    questions = [o for o in added_objects if isinstance(o, Question)]
    assert len(questions) == 1
    assert questions[0].state == "open"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_process_event_creates_detected_question_between_thresholds(monkeypatch):
    """confidence=0.7, open_threshold=0.85, candidate_threshold=0.60 → state='detected'."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CLASSIFIER_OPEN_THRESHOLD", "0.85")
    monkeypatch.setenv("CLASSIFIER_CANDIDATE_THRESHOLD", "0.60")

    from relay.config import get_settings
    get_settings.cache_clear()

    channel = make_channel(customer_slack_team_id="TCUSTOMER")

    mock_write_session = AsyncMock()
    mock_write_session.add = MagicMock()
    mock_write_session.flush = AsyncMock()

    mock_read_result = MagicMock()
    mock_read_result.scalar_one_or_none.return_value = channel
    mock_read_session = AsyncMock()
    mock_read_session.add = MagicMock()
    mock_read_session.flush = AsyncMock()
    mock_read_session.execute.return_value = mock_read_result

    @asynccontextmanager
    async def _session_ctx(workspace_id=None):
        if workspace_id is None:
            yield mock_read_session
        else:
            yield mock_write_session

    classify_result = make_classify_result(confidence=0.7)

    with patch("relay.db.session.get_session", new=_session_ctx):
        with patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=True)):
            with patch("classifier.classify.classify_message", new=AsyncMock(return_value=classify_result)):
                from relay.worker.tasks import _process_slack_event_async
                await _process_slack_event_async(make_payload())

    from relay.db.models import Question
    added_objects = [call.args[0] for call in mock_write_session.add.call_args_list]
    questions = [o for o in added_objects if isinstance(o, Question)]
    assert len(questions) == 1
    assert questions[0].state == "detected"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_process_event_skips_below_candidate_threshold(monkeypatch):
    """confidence=0.4 < candidate_threshold=0.60 → no Question created."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CLASSIFIER_OPEN_THRESHOLD", "0.85")
    monkeypatch.setenv("CLASSIFIER_CANDIDATE_THRESHOLD", "0.60")

    from relay.config import get_settings
    get_settings.cache_clear()

    channel = make_channel(customer_slack_team_id="TCUSTOMER")

    mock_write_session = AsyncMock()
    mock_write_session.add = MagicMock()
    mock_write_session.flush = AsyncMock()

    mock_read_result = MagicMock()
    mock_read_result.scalar_one_or_none.return_value = channel
    mock_read_session = AsyncMock()
    mock_read_session.add = MagicMock()
    mock_read_session.flush = AsyncMock()
    mock_read_session.execute.return_value = mock_read_result

    @asynccontextmanager
    async def _session_ctx(workspace_id=None):
        if workspace_id is None:
            yield mock_read_session
        else:
            yield mock_write_session

    classify_result = make_classify_result(confidence=0.4)

    with patch("relay.db.session.get_session", new=_session_ctx):
        with patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=True)):
            with patch("classifier.classify.classify_message", new=AsyncMock(return_value=classify_result)):
                from relay.worker.tasks import _process_slack_event_async
                await _process_slack_event_async(make_payload())

    from relay.db.models import Question
    added_objects = [call.args[0] for call in mock_write_session.add.call_args_list]
    questions = [o for o in added_objects if isinstance(o, Question)]
    assert len(questions) == 0

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_process_event_skips_duplicate_before_db_and_classifier(monkeypatch):
    """A duplicate Slack delivery should not hit DB or classifier work."""
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)

    from relay.config import get_settings
    get_settings.cache_clear()

    with (
        patch("relay.worker.tasks.claim_event_dedup_key", new=AsyncMock(return_value=False)) as mock_claim,
        patch("relay.db.session.get_session") as mock_get_session,
        patch("classifier.classify.classify_message", new=AsyncMock()) as mock_classify,
    ):
        from relay.worker.tasks import _process_slack_event_async, make_dedup_key

        payload = make_payload()
        await _process_slack_event_async(payload)

    mock_claim.assert_awaited_once_with(
        make_dedup_key(payload["team_id"], payload["channel_id"], payload["ts"]),
        ttl_seconds=get_settings().slack_event_dedup_ttl_seconds,
    )
    mock_get_session.assert_not_called()
    mock_classify.assert_not_called()

    get_settings.cache_clear()
