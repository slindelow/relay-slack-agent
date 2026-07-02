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
    handle_resolve_question,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEAM_ID = "TTEST123"


def _make_body(action_id: str, value: str, slack_user_id: str = "UACTOR") -> dict:
    return {
        "actions": [{"action_id": action_id, "value": value}],
        "user": {"id": slack_user_id},
        "team": {"id": TEAM_ID},
    }


def _make_workspace_mock(workspace_id: uuid.UUID | None = None) -> MagicMock:
    ws = MagicMock()
    ws.id = workspace_id or uuid.uuid4()
    ws.slack_team_id = TEAM_ID
    return ws


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


def _make_unscoped_session_for(workspace):
    """Build an AsyncMock session that returns the given workspace."""
    session = AsyncMock()
    ws_result = MagicMock()
    ws_result.scalar_one_or_none.return_value = workspace
    session.execute.return_value = ws_result
    return session


def _make_scoped_session_for(question, user=None):
    """Build an AsyncMock session that returns the given question and user."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

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


def _make_two_session_ctx(workspace, question, user=None):
    """
    Returns a get_session factory that yields the unscoped workspace session first,
    then the scoped question/mutation session on subsequent calls.
    """
    unscoped_session = _make_unscoped_session_for(workspace)
    scoped_session = _make_scoped_session_for(question, user)
    call_count = [0]

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        call_count[0] += 1
        if call_count[0] == 1:
            yield unscoped_session
        else:
            yield scoped_session

    return _ctx


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
    ws = _make_workspace_mock()
    q = _make_question_mock("open", workspace_id=ws.id)
    body = _make_body("relay_claim_question", str(q.id))

    ctx = _make_two_session_ctx(ws, q)

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.question.machine.claim_question", new=AsyncMock()):
            with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
                with patch("relay.worker.drafting_tasks.generate_draft_for_question.delay") as mock_draft_delay:
                    await handle_claim_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    # Claiming should kick off draft generation for the claimer.
    mock_draft_delay.assert_called_once()


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
    ws = _make_workspace_mock()

    # Unscoped returns workspace; scoped returns None for question
    unscoped_session = _make_unscoped_session_for(ws)

    scoped_session = AsyncMock()
    scoped_session.add = MagicMock()
    scoped_session.flush = AsyncMock()
    none_result = MagicMock()
    none_result.scalar_one_or_none.return_value = None
    scoped_session.execute.return_value = none_result

    call_count = [0]

    @asynccontextmanager
    async def _ctx(workspace_id=None):
        call_count[0] += 1
        if call_count[0] == 1:
            yield unscoped_session
        else:
            yield scoped_session

    with patch("relay.db.session.get_session", new=_ctx):
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
    ws = _make_workspace_mock()
    q = _make_question_mock("open", workspace_id=ws.id)
    body = _make_body("relay_snooze_1h", str(q.id))

    ctx = _make_two_session_ctx(ws, q)

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
            await handle_snooze_1h(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "Snoozed" in str(respond.call_args)


@pytest.mark.asyncio
async def test_snooze_4h_acks():
    ack = AsyncMock()
    respond = AsyncMock()
    ws = _make_workspace_mock()
    q = _make_question_mock("open", workspace_id=ws.id)
    body = _make_body("relay_snooze_4h", str(q.id))

    ctx = _make_two_session_ctx(ws, q)

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
            await handle_snooze_4h(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "4h" in str(respond.call_args)


# ---------------------------------------------------------------------------
# handle_resolve_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_question_acks_and_resolves():
    ack = AsyncMock()
    respond = AsyncMock()
    ws = _make_workspace_mock()
    q = _make_question_mock("open", workspace_id=ws.id)
    draft = MagicMock()
    draft.status = "pending"
    body = _make_body("relay_resolve_question", str(q.id))

    unscoped_session = _make_unscoped_session_for(ws)
    scoped_session = AsyncMock()
    scoped_session.add = MagicMock()

    q_result = MagicMock()
    q_result.scalar_one_or_none.return_value = q
    draft_result = MagicMock()
    draft_result.scalars.return_value = [draft]
    scoped_session.execute = AsyncMock(side_effect=[q_result, draft_result])

    call_count = [0]

    @asynccontextmanager
    async def ctx(workspace_id=None):
        call_count[0] += 1
        if call_count[0] == 1:
            yield unscoped_session
        else:
            yield scoped_session

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.question.machine.resolve_question", new=AsyncMock()) as mock_resolve:
            with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
                await handle_resolve_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    mock_resolve.assert_awaited_once()
    respond.assert_awaited_once()
    assert "marked resolved" in str(respond.call_args).lower()
    assert draft.status == "discarded"


# ---------------------------------------------------------------------------
# handle_mark_not_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_not_question_acks_and_resolves():
    ack = AsyncMock()
    respond = AsyncMock()
    ws = _make_workspace_mock()
    q = _make_question_mock("open", workspace_id=ws.id)
    body = _make_body("relay_mark_not_question", str(q.id))

    ctx = _make_two_session_ctx(ws, q)

    with patch("relay.db.session.get_session", new=ctx):
        with patch("relay.question.machine.resolve_question", new=AsyncMock()):
            with patch("relay.slack.actions._get_or_create_user", new=AsyncMock(return_value=_make_user_mock())):
                await handle_mark_not_question(ack=ack, body=body, respond=respond)

    ack.assert_awaited_once()
    respond.assert_awaited_once()
    assert "not a question" in str(respond.call_args).lower()
