"""Unit tests for relay/slack/actions.py — no real DB or Slack API."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.slack.actions import (
    _parse_question_id,
    handle_claim_question,
    handle_snooze_1h,
    handle_snooze_4h,
    handle_mark_not_question,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_body(action_id: str, value: str, slack_user_id: str = "UACTOR") -> dict:
    return {
        "actions": [{"action_id": action_id, "value": value}],
        "user": {"id": slack_user_id},
    }


def _make_question_mock(state: str = "open", workspace_id: uuid.UUID | None = None) -> MagicMock:
    q = MagicMock()
    q.id = uuid.uuid4()
    q.workspace_id = workspace_id or uuid.uuid4()
    q.state = state
    q.alert_count = 0
    q.next_alert_at = None
    return q


def _make_user_mock() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.slack_user_id = "UACTOR"
    u.is_ooo = False
    return u


def _make_session_for(question, user=None):
    """Build an AsyncMock session that returns the given question and user."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    def _execute_side_effect(stmt, *args, **kwargs):
        result = MagicMock()
        # First call returns question, second returns user
        result.scalar_one_or_none.return_value = question if user is None else None
        return result

    q_result = MagicMock()
    q_result.scalar_one_or_none.return_value = question

    u_result = MagicMock()
    u_result.scalar_one_or_none.return_value = user or _make_user_mock()

    call_count = [0]

    async def _execute(stmt, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return q_result
        return u_result

    session.execute.side_effect = _execute
    return session


@asynccontextmanager
async def _session_ctx(workspace_id=None):
    """Yield a minimal mock session."""
    yield AsyncMock()


# ---------------------------------------------------------------------------
# _parse_question_id
# ---------------------------------------------------------------------------


def test_parse_question_id_valid():
    q_id = uuid.uuid4()
    assert _parse_question_id(str(q_id)) == q_id


def test_parse_question_id_invalid():
    assert _parse_question_id("not-a-uuid") is None


def test_parse_question_id_empty():
    assert _parse_question_id("") is None


# ---------------------------------------------------------------------------
# handle_claim_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_question_acks_immediately():
    """ack() must be called regardless of success/failure."""
    ack = AsyncMock()
    respond = AsyncMock()
    q = _make_question_mock("open")
    body = _make_body("relay_claim_question", str(q.id))

    async def _session_ctx_scoped(workspace_id=None):
        session = _make_session_for(q)

        @asynccontextmanager
        async def _ctx(workspace_id=workspace_id):
            yield session

        return _ctx

    ctx = await _session_ctx_scoped()

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.question.machine.claim_question", new=AsyncMock()):
            with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
                await handle_claim_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_question_invalid_uuid_responds_ephemeral():
    ack = AsyncMock()
    respond = AsyncMock()
    body = _make_body("relay_claim_question", "bad-uuid")

    await handle_claim_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    call_kwargs = respond.call_args
    assert "ephemeral" in str(call_kwargs)


@pytest.mark.asyncio
async def test_claim_question_question_not_found_responds():
    ack = AsyncMock()
    respond = AsyncMock()
    q_id = uuid.uuid4()
    body = _make_body("relay_claim_question", str(q_id))

    @asynccontextmanager
    async def _none_session(workspace_id=None):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        yield session

    with patch("relay.db.session.get_session", new=_none_session):
        await handle_claim_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "not found" in respond.call_args.kwargs.get("text", "") or "not found" in str(respond.call_args)


# ---------------------------------------------------------------------------
# handle_snooze_1h / handle_snooze_4h
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snooze_1h_acks():
    ack = AsyncMock()
    respond = AsyncMock()
    q = _make_question_mock("open")
    body = _make_body("relay_snooze_1h", str(q.id))

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = q
        session.execute.return_value = result
        yield session

    with patch("relay.db.session.get_session", new=_ctx):
        with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
            await handle_snooze_1h(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "Snoozed" in str(respond.call_args)


@pytest.mark.asyncio
async def test_snooze_4h_acks():
    ack = AsyncMock()
    respond = AsyncMock()
    q = _make_question_mock("open")
    body = _make_body("relay_snooze_4h", str(q.id))

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = q
        session.execute.return_value = result
        yield session

    with patch("relay.db.session.get_session", new=_ctx):
        with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
            await handle_snooze_4h(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "4h" in str(respond.call_args)


# ---------------------------------------------------------------------------
# handle_mark_not_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_not_question_acks_and_resolves():
    ack = AsyncMock()
    respond = AsyncMock()
    q = _make_question_mock("open")
    body = _make_body("relay_mark_not_question", str(q.id))

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = q
        session.execute.return_value = result
        yield session

    with patch("relay.db.session.get_session", new=_ctx):
        with patch("relay.question.machine.resolve_question", new=AsyncMock()):
            with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
                await handle_mark_not_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "not a question" in str(respond.call_args).lower()
