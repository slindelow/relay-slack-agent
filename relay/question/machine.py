"""Question state machine — deterministic state transitions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.models import Question, QuestionEvent, QuestionState


class InvalidStateTransition(Exception):
    def __init__(self, question_id: uuid.UUID, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Cannot transition question {question_id} from {from_state} to {to_state}"
        )
        self.question_id = question_id
        self.from_state = from_state
        self.to_state = to_state


async def _load_question(session: AsyncSession, question_id: uuid.UUID) -> Question:
    result = await session.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if question is None:
        raise ValueError(f"Question {question_id} not found")
    return question


async def open_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> Question:
    question = await _load_question(session, question_id)
    if question.state != QuestionState.detected.value:
        raise InvalidStateTransition(question_id, question.state, QuestionState.open.value)
    question.state = QuestionState.open.value
    session.add(
        QuestionEvent(
            question_id=question.id,
            workspace_id=question.workspace_id,
            event_type="opened",
            actor_user_id=actor_user_id,
        )
    )
    await session.flush()
    return question


async def claim_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Question:
    question = await _load_question(session, question_id)
    if question.state != QuestionState.open.value:
        raise InvalidStateTransition(question_id, question.state, QuestionState.claimed.value)
    question.state = QuestionState.claimed.value
    question.claimed_at = datetime.now(UTC)
    session.add(
        QuestionEvent(
            question_id=question.id,
            workspace_id=question.workspace_id,
            event_type="claimed",
            actor_user_id=actor_user_id,
        )
    )
    await session.flush()
    return question


async def resolve_question(
    session: AsyncSession,
    question_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> Question:
    question = await _load_question(session, question_id)
    valid_states = {QuestionState.open.value, QuestionState.claimed.value}
    if question.state not in valid_states:
        raise InvalidStateTransition(question_id, question.state, QuestionState.resolved.value)
    question.state = QuestionState.resolved.value
    question.resolved_at = datetime.now(UTC)
    session.add(
        QuestionEvent(
            question_id=question.id,
            workspace_id=question.workspace_id,
            event_type="resolved",
            actor_user_id=actor_user_id,
        )
    )
    await session.flush()
    return question


async def expire_question(
    session: AsyncSession,
    question_id: uuid.UUID,
) -> Question:
    question = await _load_question(session, question_id)
    valid_states = {QuestionState.open.value, QuestionState.claimed.value}
    if question.state not in valid_states:
        raise InvalidStateTransition(question_id, question.state, QuestionState.expired.value)
    question.state = QuestionState.expired.value
    question.expired_at = datetime.now(UTC)
    session.add(
        QuestionEvent(
            question_id=question.id,
            workspace_id=question.workspace_id,
            event_type="expired",
            actor_user_id=None,
        )
    )
    await session.flush()
    return question
