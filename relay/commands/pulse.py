"""Handler logic for the /relay pulse subcommand."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from relay.db.models import CustomerAccount, ImpactMetric, Question, QuestionState, User, Workspace
from relay.db.session import get_session
from relay.slack.draft_modal import _renewal_proximity

logger = logging.getLogger(__name__)

_OPEN_STATES = {
    QuestionState.detected.value,
    QuestionState.open.value,
    QuestionState.claimed.value,
}


@dataclass
class AccountPulse:
    account: CustomerAccount
    open_count: int
    sla_rate: str = "n/a"
    last_resolved: str = "N/A"


def _parse_pulse_query(text: str) -> str:
    stripped = text.strip()
    if stripped.lower().startswith("pulse"):
        stripped = stripped[len("pulse"):].strip()
    return stripped


def _arr(value) -> str:
    if value is None:
        return "N/A"
    return f"${float(value):,.0f}"


def _owner_text(account: CustomerAccount) -> str:
    owner = getattr(account, "owner", None)
    backup = getattr(account, "backup_owner", None)
    if owner is not None and getattr(owner, "is_ooo", False) and backup is not None:
        return f"Owner OOO; backup: {backup.display_name or backup.slack_user_id}"
    if owner is not None:
        return owner.display_name or owner.slack_user_id
    if backup is not None:
        return f"Backup: {backup.display_name or backup.slack_user_id}"
    return "Unassigned"


def _sla_rate(metrics: list[ImpactMetric]) -> str:
    values = [metric.sla_met for metric in metrics if metric.sla_met is not None]
    if not values:
        return "n/a"
    return f"{(sum(1 for value in values if value) / len(values)) * 100:.1f}%"


def _renewal_text(account: CustomerAccount) -> str:
    renewal = getattr(account, "renewal_date", None)
    if isinstance(renewal, date):
        return _renewal_proximity(renewal.isoformat())
    return _renewal_proximity(renewal)


def _summary_blocks(pulses: list[AccountPulse]) -> list[dict]:
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Account Pulse*"}},
    ]
    if not pulses:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No accounts have open questions right now._"},
        })
        return blocks

    for pulse in pulses:
        account = pulse.account
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{account.name}* - {pulse.open_count} open\n"
                    f"Tier: `{account.tier}` · ARR: {_arr(account.arr)} · Renewal: {_renewal_text(account)}\n"
                    f"Owner: {_owner_text(account)}"
                ),
            },
        })
    return blocks


def _detail_blocks(pulse: AccountPulse) -> list[dict]:
    account = pulse.account
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Account Pulse: {account.name}*"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Open questions*\n{pulse.open_count}"},
                {"type": "mrkdwn", "text": f"*SLA met rate (30d)*\n{pulse.sla_rate}"},
                {"type": "mrkdwn", "text": f"*Last resolved*\n{pulse.last_resolved}"},
                {"type": "mrkdwn", "text": f"*Renewal*\n{_renewal_text(account)}"},
                {"type": "mrkdwn", "text": f"*Tier*\n{account.tier}"},
                {"type": "mrkdwn", "text": f"*ARR*\n{_arr(account.arr)}"},
                {"type": "mrkdwn", "text": f"*Owner*\n{_owner_text(account)}"},
            ],
        },
    ]


async def _workspace_for_team(slack_team_id: str) -> Workspace | None:
    async with get_session() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.slack_team_id == slack_team_id)
        )
        return result.scalar_one_or_none()


async def _top_account_pulses(workspace_id: uuid.UUID, session) -> list[AccountPulse]:
    count_result = await session.execute(
        select(Question.account_id, func.count(Question.id).label("open_count"))
        .where(
            Question.workspace_id == workspace_id,
            Question.state.in_(_OPEN_STATES),
        )
        .group_by(Question.account_id)
        .order_by(desc("open_count"))
        .limit(5)
    )
    rows = count_result.all()
    account_ids = [row.account_id for row in rows]
    if not account_ids:
        return []

    account_result = await session.execute(
        select(CustomerAccount)
        .options(selectinload(CustomerAccount.owner), selectinload(CustomerAccount.backup_owner))
        .where(
            CustomerAccount.workspace_id == workspace_id,
            CustomerAccount.id.in_(account_ids),
            CustomerAccount.deleted_at.is_(None),
        )
    )
    accounts = {account.id: account for account in account_result.scalars()}
    return [
        AccountPulse(account=accounts[row.account_id], open_count=row.open_count)
        for row in rows
        if row.account_id in accounts
    ]


async def _account_detail_pulse(workspace_id: uuid.UUID, session, query: str) -> AccountPulse | None:
    account_result = await session.execute(
        select(CustomerAccount)
        .options(selectinload(CustomerAccount.owner), selectinload(CustomerAccount.backup_owner))
        .where(
            CustomerAccount.workspace_id == workspace_id,
            CustomerAccount.deleted_at.is_(None),
            CustomerAccount.name.ilike(f"%{query}%"),
        )
        .limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        return None

    open_result = await session.execute(
        select(func.count())
        .select_from(Question)
        .where(
            Question.workspace_id == workspace_id,
            Question.account_id == account.id,
            Question.state.in_(_OPEN_STATES),
        )
    )
    open_count = open_result.scalar_one()

    metric_result = await session.execute(
        select(ImpactMetric).where(
            ImpactMetric.workspace_id == workspace_id,
            ImpactMetric.account_id == account.id,
            ImpactMetric.created_at >= datetime.now(UTC) - timedelta(days=30),
        )
    )
    metrics = list(metric_result.scalars())

    resolved_result = await session.execute(
        select(Question.resolved_at)
        .where(
            Question.workspace_id == workspace_id,
            Question.account_id == account.id,
            Question.state == QuestionState.resolved.value,
            Question.resolved_at.is_not(None),
        )
        .order_by(Question.resolved_at.desc())
        .limit(1)
    )
    resolved_at = resolved_result.scalar_one_or_none()
    last_resolved = resolved_at.date().isoformat() if resolved_at else "N/A"

    return AccountPulse(
        account=account,
        open_count=open_count,
        sla_rate=_sla_rate(metrics),
        last_resolved=last_resolved,
    )


async def handle_pulse(ack, respond, command) -> None:
    """Handle `/relay pulse [account-name]`."""
    await ack()

    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to build pulse: missing Slack workspace id.")
        return

    query = _parse_pulse_query(command.get("text") or "")

    try:
        workspace = await _workspace_for_team(slack_team_id)
        if workspace is None:
            await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
            return

        async with get_session(workspace.id) as session:
            if query:
                pulse = await _account_detail_pulse(workspace.id, session, query)
                if pulse is None:
                    await respond(response_type="ephemeral", text="Account not found. Run `/relay register` to add it.")
                    return
                blocks = _detail_blocks(pulse)
            else:
                blocks = _summary_blocks(await _top_account_pulses(workspace.id, session))
    except Exception as exc:
        logger.exception("pulse_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Pulse failed: {type(exc).__name__}")
        return

    await respond(response_type="ephemeral", blocks=blocks)
