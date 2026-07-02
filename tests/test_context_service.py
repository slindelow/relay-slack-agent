from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from relay.context.contracts import ContextSource
from relay.context.service import assemble_evidence_for_question, search_customer_history, search_slack_context
from relay.db.models import ContextToolLog, CustomerAccount, Message, MonitoredChannel, Question, User
from relay.slack.oauth import upsert_workspace_from_install


async def _seed_question(session):
    workspace = await upsert_workspace_from_install(session, "T_CONTEXT", "Context Corp")
    await session.flush()
    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )
    user = User(
        workspace_id=workspace.id,
        slack_user_id="U_CSM",
        relay_role="csm",
    )
    account = CustomerAccount(
        workspace_id=workspace.id,
        name="Acme",
        tier="enterprise",
        arr=120000,
        health_score=82,
        lifecycle_stage="renewal",
    )
    session.add_all([user, account])
    await session.flush()
    channel = MonitoredChannel(
        workspace_id=workspace.id,
        account_id=account.id,
        slack_channel_id="C_CUSTOMER",
        slack_channel_name="ext-acme",
        customer_slack_team_id="T_EXT",
        is_ext_shared=True,
    )
    session.add(channel)
    await session.flush()
    message = Message(
        workspace_id=workspace.id,
        channel_id=channel.id,
        slack_message_ts="1710000000.000100",
        sender_slack_user_id="U_EXT",
        sender_slack_team_id="T_EXT",
        is_customer_message=True,
        raw_excerpt="How do we rotate the SSO certificate?",
    )
    session.add(message)
    await session.flush()
    question = Question(
        workspace_id=workspace.id,
        channel_id=channel.id,
        message_id=message.id,
        account_id=account.id,
        state="claimed",
        urgency="high",
        title_excerpt="SSO certificate rotation",
    )
    session.add(question)
    await session.flush()
    return workspace, user, question


@pytest.mark.asyncio
async def test_assemble_evidence_for_question_merges_sources_and_logs(db_session):
    workspace, _user, question = await _seed_question(db_session)
    indexed = ContextSource(
        title="SSO runbook",
        provider="google_drive",
        url="https://docs.example.com/sso",
        excerpt="Rotate the certificate in admin settings.",
        freshness_ts=datetime.now(UTC),
        visibility="customer_safe",
    )
    slack = ContextSource(
        title="Slack search result",
        provider="slack_rts",
        url="https://example.slack.com/archives/C123/p1",
        excerpt="Internal team confirmed the new SSO cert steps yesterday.",
        freshness_ts=datetime.now(UTC),
        visibility="internal",
    )

    with (
        patch("relay.context.service.search_indexed_knowledge", new=AsyncMock(return_value=[indexed])),
        patch("relay.context.service.search_slack_context", new=AsyncMock(return_value=[slack])),
    ):
        bundle = await assemble_evidence_for_question(
            workspace.id,
            question.id,
            db_session,
            acting_slack_user_id="U_CSM",
        )

    assert bundle.question_excerpt == "How do we rotate the SSO certificate?"
    assert bundle.account_context["name"] == "Acme"
    assert {source.provider for source in bundle.sources} == {"google_drive", "slack_rts"}
    assert next(source for source in bundle.sources if source.provider == "slack_rts").visibility == "internal"

    log_result = await db_session.execute(
        select(ContextToolLog.tool_name).where(ContextToolLog.workspace_id == workspace.id)
    )
    assert "assemble_evidence_for_question" in set(log_result.scalars())


@pytest.mark.asyncio
async def test_search_slack_context_missing_token_returns_empty_and_logs(db_session):
    workspace, _user, _question = await _seed_question(db_session)

    results = await search_slack_context(
        workspace.id,
        "U_CSM",
        "How do we rotate SSO?",
        db_session,
    )

    assert results == []
    log_result = await db_session.execute(
        select(ContextToolLog).where(
            ContextToolLog.workspace_id == workspace.id,
            ContextToolLog.tool_name == "search_slack_context",
        )
    )
    log = log_result.scalar_one()
    assert log.metadata_json["error"] == "not_connected"


@pytest.mark.asyncio
async def test_search_slack_context_api_error_returns_empty_and_logs(db_session):
    workspace, _user, _question = await _seed_question(db_session)
    fake_client = AsyncMock()
    fake_client.search_internal_context.side_effect = RuntimeError("slack unavailable")

    results = await search_slack_context(
        workspace.id,
        "U_CSM",
        "How do we rotate SSO?",
        db_session,
        rts_client=fake_client,
    )

    assert results == []
    log_result = await db_session.execute(
        select(ContextToolLog)
        .where(
            ContextToolLog.workspace_id == workspace.id,
            ContextToolLog.tool_name == "search_slack_context",
        )
        .order_by(ContextToolLog.created_at.desc())
    )
    log = log_result.scalars().first()
    assert log.metadata_json["error"] == "slack_api_error"


@pytest.mark.asyncio
async def test_search_customer_history_returns_recent_customer_messages(db_session):
    workspace, _user, _question = await _seed_question(db_session)

    results = await search_customer_history(
        workspace.id,
        "what is the customer's main concern?",
        db_session,
        actor_slack_user_id="U_CSM",
    )

    assert len(results) == 1
    assert results[0].provider == "customer_history"
    assert "How do we rotate the SSO certificate?" in results[0].excerpt
    log_result = await db_session.execute(
        select(ContextToolLog).where(
            ContextToolLog.workspace_id == workspace.id,
            ContextToolLog.tool_name == "search_customer_history",
        )
    )
    assert log_result.scalar_one().metadata_json["message_count"] == 1
