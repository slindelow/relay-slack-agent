"""Integration tests for RLS tenant isolation.

These tests prove that the workspace_isolation RLS policy correctly:
- Shows workspace A's rows when the context is set to workspace A.
- Shows workspace B's rows when the context is set to workspace B.
- Returns no tenant rows when the context is unset.
- Leaves the workspaces table itself readable without context (it is not tenant-scoped).

Requires a live PostgreSQL test database (see tests/conftest.py).
Tests are skipped automatically when the database is not reachable.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from relay.db.models import (
    Alert,
    Assignment,
    CustomerAccount,
    Message,
    MonitoredChannel,
    Question,
    QuestionEvent,
    SlaPolicy,
    Snooze,
    User,
    Workspace,
    WorkspaceSettings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _create_workspace(session, team_id: str, team_name: str = "Test") -> Workspace:
    ws = Workspace(slack_team_id=team_id, slack_team_name=team_name)
    session.add(ws)
    await session.flush()
    await _set_context(session, ws.id)
    session.add(WorkspaceSettings(workspace_id=ws.id))
    for tier, resp, esc in (("enterprise", 30, 45), ("pro", 120, 180), ("starter", 480, 600)):
        session.add(SlaPolicy(workspace_id=ws.id, tier_name=tier, response_window_minutes=resp, escalation_window_minutes=esc))
    await session.flush()
    return ws


async def _create_question_stack(session, workspace: Workspace, suffix: str) -> Question:
    await _set_context(session, workspace.id)
    owner = User(
        workspace_id=workspace.id,
        slack_user_id=f"U_OWNER_{suffix}",
    )
    session.add(owner)
    await session.flush()

    sla_policy = (
        await session.execute(
            select(SlaPolicy).where(
                SlaPolicy.workspace_id == workspace.id,
                SlaPolicy.tier_name == "enterprise",
            )
        )
    ).scalar_one()
    account = CustomerAccount(
        workspace_id=workspace.id,
        name=f"Account {suffix}",
        domain=f"{suffix.lower()}.example.com",
        crm_provider="hubspot",
        external_crm_id=f"hubspot-{suffix}",
        tier="enterprise",
        sla_policy_id=sla_policy.id,
        owner_user_id=owner.id,
    )
    session.add(account)
    await session.flush()

    channel = MonitoredChannel(
        workspace_id=workspace.id,
        account_id=account.id,
        slack_channel_id=f"C_{suffix}",
        customer_slack_team_id=f"T_CUSTOMER_{suffix}",
        is_ext_shared=True,
    )
    session.add(channel)
    await session.flush()

    message = Message(
        workspace_id=workspace.id,
        channel_id=channel.id,
        slack_message_ts=f"1710000000.{suffix[-3:]}",
        is_customer_message=True,
        raw_excerpt="Is the API down?",
        classification_label=True,
        classification_confidence=0.92,
        classification_variant="a",
    )
    session.add(message)
    await session.flush()

    question = Question(
        workspace_id=workspace.id,
        channel_id=channel.id,
        message_id=message.id,
        account_id=account.id,
        state="open",
        urgency="high",
        title_excerpt="Is the API down?",
    )
    session.add(question)
    await session.flush()

    session.add(
        QuestionEvent(
            workspace_id=workspace.id,
            question_id=question.id,
            event_type="question.opened",
            event_metadata={"source": "test"},
        )
    )
    await session.flush()
    return question


async def _set_context(session, workspace_id):
    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :wid, true)"),
        {"wid": str(workspace_id)},
    )


async def _clear_context(session):
    await session.execute(text("SELECT set_config('app.current_workspace_id', '', true)"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_a_cannot_see_workspace_b_settings(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_001_A")
    ws_b = await _create_workspace(db_session, "T_RLS_001_B")

    await _set_context(db_session, ws_a.id)

    result = await db_session.execute(select(WorkspaceSettings))
    visible = {row.workspace_id for row in result.scalars().all()}

    assert ws_a.id in visible
    assert ws_b.id not in visible


@pytest.mark.asyncio
async def test_workspace_b_cannot_see_workspace_a_settings(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_002_A")
    ws_b = await _create_workspace(db_session, "T_RLS_002_B")

    await _set_context(db_session, ws_b.id)

    result = await db_session.execute(select(WorkspaceSettings))
    visible = {row.workspace_id for row in result.scalars().all()}

    assert ws_b.id in visible
    assert ws_a.id not in visible


@pytest.mark.asyncio
async def test_no_context_returns_no_tenant_rows(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_003_A")
    ws_b = await _create_workspace(db_session, "T_RLS_003_B")
    await _create_question_stack(db_session, ws_a, "RLS003A")
    await _create_question_stack(db_session, ws_b, "RLS003B")

    await _clear_context(db_session)

    settings_result = await db_session.execute(select(WorkspaceSettings))
    assert settings_result.scalars().all() == []

    sla_result = await db_session.execute(select(SlaPolicy))
    assert sla_result.scalars().all() == []

    for model in (CustomerAccount, MonitoredChannel, Message, Question, QuestionEvent):
        result = await db_session.execute(select(model))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_workspaces_table_readable_without_context(db_session):
    ws = await _create_workspace(db_session, "T_RLS_004")
    await _clear_context(db_session)

    result = await db_session.execute(
        select(Workspace).where(Workspace.slack_team_id == "T_RLS_004")
    )
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.id == ws.id


@pytest.mark.asyncio
async def test_sla_policies_respect_rls(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_005_A")
    ws_b = await _create_workspace(db_session, "T_RLS_005_B")

    await _set_context(db_session, ws_a.id)
    result = await db_session.execute(select(SlaPolicy))
    workspace_ids = {row.workspace_id for row in result.scalars().all()}

    assert ws_a.id in workspace_ids
    assert ws_b.id not in workspace_ids


@pytest.mark.asyncio
async def test_context_switch_changes_visible_rows(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_006_A")
    ws_b = await _create_workspace(db_session, "T_RLS_006_B")

    await _set_context(db_session, ws_a.id)
    result_a = await db_session.execute(select(WorkspaceSettings))
    ids_as_a = {row.workspace_id for row in result_a.scalars().all()}

    await _set_context(db_session, ws_b.id)
    result_b = await db_session.execute(select(WorkspaceSettings))
    ids_as_b = {row.workspace_id for row in result_b.scalars().all()}

    assert ws_a.id in ids_as_a
    assert ws_b.id not in ids_as_a

    assert ws_b.id in ids_as_b
    assert ws_a.id not in ids_as_b


@pytest.mark.asyncio
async def test_plan_2_question_tables_respect_rls(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_007_A")
    ws_b = await _create_workspace(db_session, "T_RLS_007_B")
    question_a = await _create_question_stack(db_session, ws_a, "RLS007A")
    question_b = await _create_question_stack(db_session, ws_b, "RLS007B")

    await _set_context(db_session, ws_a.id)

    account_ids = {row.workspace_id for row in (await db_session.execute(select(CustomerAccount))).scalars().all()}
    channel_ids = {row.workspace_id for row in (await db_session.execute(select(MonitoredChannel))).scalars().all()}
    message_ids = {row.workspace_id for row in (await db_session.execute(select(Message))).scalars().all()}
    question_ids = {row.id for row in (await db_session.execute(select(Question))).scalars().all()}
    event_workspace_ids = {row.workspace_id for row in (await db_session.execute(select(QuestionEvent))).scalars().all()}

    assert account_ids == {ws_a.id}
    assert channel_ids == {ws_a.id}
    assert message_ids == {ws_a.id}
    assert question_ids == {question_a.id}
    assert question_b.id not in question_ids
    assert event_workspace_ids == {ws_a.id}


@pytest.mark.asyncio
async def test_plan_3_sla_tables_respect_rls(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_009_A")
    ws_b = await _create_workspace(db_session, "T_RLS_009_B")
    question_a = await _create_question_stack(db_session, ws_a, "RLS009A")
    question_b = await _create_question_stack(db_session, ws_b, "RLS009B")

    for workspace, question in ((ws_a, question_a), (ws_b, question_b)):
        await _set_context(db_session, workspace.id)
        owner = (
            await db_session.execute(
                select(User).where(User.workspace_id == workspace.id)
            )
        ).scalars().first()
        assert owner is not None

        db_session.add(
            Alert(
                workspace_id=workspace.id,
                question_id=question.id,
                recipient_user_id=owner.id,
                alert_type="primary",
            )
        )
        db_session.add(
            Snooze(
                workspace_id=workspace.id,
                question_id=question.id,
                snoozed_by_user_id=owner.id,
                snoozed_until=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db_session.add(
            Assignment(
                workspace_id=workspace.id,
                question_id=question.id,
                assignee_user_id=owner.id,
                assigned_by_user_id=owner.id,
            )
        )
        await db_session.flush()

    await _set_context(db_session, ws_a.id)

    alert_workspace_ids = {
        row.workspace_id
        for row in (await db_session.execute(select(Alert))).scalars().all()
    }
    snooze_workspace_ids = {
        row.workspace_id
        for row in (await db_session.execute(select(Snooze))).scalars().all()
    }
    assignment_workspace_ids = {
        row.workspace_id
        for row in (await db_session.execute(select(Assignment))).scalars().all()
    }

    assert alert_workspace_ids == {ws_a.id}
    assert snooze_workspace_ids == {ws_a.id}
    assert assignment_workspace_ids == {ws_a.id}
    assert question_b.id not in {
        row.question_id
        for row in (await db_session.execute(select(Alert))).scalars().all()
    }


@pytest.mark.asyncio
async def test_tenant_scoped_foreign_keys_reject_cross_workspace_parent_refs(db_session):
    ws_a = await _create_workspace(db_session, "T_RLS_008_A")
    ws_b = await _create_workspace(db_session, "T_RLS_008_B")

    await _set_context(db_session, ws_b.id)
    account_b = CustomerAccount(
        workspace_id=ws_b.id,
        name="Workspace B Account",
        crm_provider="hubspot",
        external_crm_id="hubspot-cross-tenant",
        tier="enterprise",
    )
    db_session.add(account_b)
    await db_session.flush()

    await _set_context(db_session, ws_a.id)
    db_session.add(
        MonitoredChannel(
            workspace_id=ws_a.id,
            account_id=account_b.id,
            slack_channel_id="C_CROSS_TENANT",
            customer_slack_team_id="T_CUSTOMER_CROSS",
            is_ext_shared=True,
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()
