"""Unit tests for relay/question/machine.py — no real DB required."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from relay.db.models import Question, QuestionEvent
from relay.question.machine import (
    InvalidStateTransition,
    claim_question,
    expire_question,
    open_question,
    resolve_question,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_question(state: str) -> Question:
    q = MagicMock(spec=Question)
    q.id = uuid.uuid4()
    q.workspace_id = uuid.uuid4()
    q.state = state
    q.claimed_at = None
    q.resolved_at = None
    q.expired_at = None
    return q


def make_mock_session(question: Question) -> AsyncMock:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = question
    session.execute.return_value = mock_result
    # session.add is synchronous; override to avoid coroutine warnings
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# open_question
# ---------------------------------------------------------------------------


async def test_open_question_transitions_detected_to_open() -> None:
    q = make_question("detected")
    session = make_mock_session(q)
    result = await open_question(session, q.id)
    assert result.state == "open"


async def test_open_question_raises_on_invalid_state() -> None:
    q = make_question("open")
    session = make_mock_session(q)
    with pytest.raises(InvalidStateTransition):
        await open_question(session, q.id)


# ---------------------------------------------------------------------------
# claim_question
# ---------------------------------------------------------------------------


async def test_claim_question_transitions_open_to_claimed() -> None:
    q = make_question("open")
    session = make_mock_session(q)
    actor = uuid.uuid4()
    result = await claim_question(session, q.id, actor)
    assert result.state == "claimed"
    assert result.claimed_at is not None


async def test_claim_question_raises_on_invalid_state() -> None:
    q = make_question("detected")
    session = make_mock_session(q)
    with pytest.raises(InvalidStateTransition):
        await claim_question(session, q.id, uuid.uuid4())


# ---------------------------------------------------------------------------
# resolve_question
# ---------------------------------------------------------------------------


async def test_resolve_question_from_open() -> None:
    q = make_question("open")
    session = make_mock_session(q)
    result = await resolve_question(session, q.id)
    assert result.state == "resolved"
    assert result.resolved_at is not None


async def test_resolve_question_from_claimed() -> None:
    q = make_question("claimed")
    session = make_mock_session(q)
    result = await resolve_question(session, q.id)
    assert result.state == "resolved"


async def test_resolve_question_raises_on_invalid_state() -> None:
    q = make_question("detected")
    session = make_mock_session(q)
    with pytest.raises(InvalidStateTransition):
        await resolve_question(session, q.id)


# ---------------------------------------------------------------------------
# expire_question
# ---------------------------------------------------------------------------


async def test_expire_question_from_open() -> None:
    q = make_question("open")
    session = make_mock_session(q)
    result = await expire_question(session, q.id)
    assert result.state == "expired"
    assert result.expired_at is not None


async def test_expire_question_raises_on_invalid_state() -> None:
    q = make_question("resolved")
    session = make_mock_session(q)
    with pytest.raises(InvalidStateTransition):
        await expire_question(session, q.id)


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


async def test_question_event_added_on_transition() -> None:
    q = make_question("detected")
    session = make_mock_session(q)
    await open_question(session, q.id, actor_user_id=uuid.uuid4())
    # session.add should have been called at least once with a QuestionEvent
    added_objects = [call.args[0] for call in session.add.call_args_list]
    assert any(isinstance(obj, QuestionEvent) for obj in added_objects)
