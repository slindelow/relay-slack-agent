"""Handler logic for the /relay register subcommand."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import func, select

from relay.db.models import CustomerAccount, SlaPolicy, User, Workspace
from relay.db.session import get_session
from relay.slack.channel import register_channel

logger = logging.getLogger(__name__)

VALID_TIERS = {"enterprise", "pro", "starter"}

# Matches Slack channel mentions like <#C123456|channel-name>
_CHANNEL_MENTION_RE = re.compile(r"^<#([A-Z0-9]+)\|([^>]+)>$")

# Matches Slack user mentions like <@U123456> or <@U123456|display-name>
_USER_MENTION_RE = re.compile(r"^<@([A-Z0-9]+)(?:\|[^>]+)?>$")


def _parse_register_args(text: str) -> tuple[str, str, str, str, str | None] | None:
    """Parse the arguments after 'register'.

    Expected:
        #channel-name account-name tier [@owner]
        <#C123456|channel-name> account-name tier [@owner]

    Returns (channel_id_or_name, channel_display_name, account_name, tier, owner_slack_user_id)
    or None if parsing fails.
    """
    stripped = text.strip()
    if stripped.lower().startswith("register"):
        stripped = stripped[len("register"):].strip()
    if not stripped:
        return None

    tokens = stripped.split()
    if len(tokens) < 3:
        return None

    channel_token = tokens[0]
    mention_match = _CHANNEL_MENTION_RE.match(channel_token)
    if mention_match:
        channel_id = mention_match.group(1)
        channel_display_name = mention_match.group(2)
    elif channel_token.startswith("#"):
        channel_id = channel_token[1:]
        channel_display_name = channel_id
    else:
        return None

    remaining_tokens = tokens[1:]
    owner_slack_user_id = None
    if remaining_tokens and (owner_match := _USER_MENTION_RE.match(remaining_tokens[-1])):
        owner_slack_user_id = owner_match.group(1)
        remaining_tokens = remaining_tokens[:-1]

    if len(remaining_tokens) < 2:
        return None

    tier = remaining_tokens[-1].lower()
    if tier not in VALID_TIERS:
        return None

    account_name = " ".join(remaining_tokens[:-1])
    if not account_name:
        return None

    return channel_id, channel_display_name, account_name, tier, owner_slack_user_id


async def _get_or_create_user(session, workspace_id: UUID, slack_user_id: str) -> User:
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(workspace_id=workspace_id, slack_user_id=slack_user_id)
    session.add(user)
    await session.flush()
    return user


async def _get_or_create_account(
    session,
    workspace_id: UUID,
    account_name: str,
    tier: str,
    owner_user_id: UUID | None,
) -> CustomerAccount:
    result = await session.execute(
        select(CustomerAccount).where(
            CustomerAccount.workspace_id == workspace_id,
            func.lower(CustomerAccount.name) == account_name.lower(),
            CustomerAccount.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()

    sla_result = await session.execute(
        select(SlaPolicy).where(
            SlaPolicy.workspace_id == workspace_id,
            SlaPolicy.tier_name == tier,
        )
    )
    sla_policy = sla_result.scalar_one_or_none()

    if account is None:
        account = CustomerAccount(
            workspace_id=workspace_id,
            name=account_name,
            tier=tier,
            owner_user_id=owner_user_id,
            sla_policy_id=sla_policy.id if sla_policy else None,
        )
        session.add(account)
        await session.flush()
        return account

    account.tier = tier
    account.sla_policy_id = sla_policy.id if sla_policy else account.sla_policy_id
    if owner_user_id is not None:
        account.owner_user_id = owner_user_id
    return account


async def _fetch_channel_metadata(client, channel_id: str, installer_team_id: str | None) -> tuple[str | None, bool]:
    if client is None or not channel_id.startswith("C"):
        return None, False

    response = await client.conversations_info(channel=channel_id)
    channel = response.get("channel", {})
    shared_team_ids = channel.get("shared_team_ids") or []
    customer_team_id = next((team_id for team_id in shared_team_ids if team_id != installer_team_id), None)
    return customer_team_id, bool(channel.get("is_ext_shared"))


async def handle_register(ack, respond, command, client=None) -> None:
    """Handle `/relay register #channel account-name tier [@owner]`."""
    await ack()

    parsed = _parse_register_args((command.get("text") or "").strip())
    if parsed is None:
        await respond(
            response_type="ephemeral",
            text="Usage: /relay register #channel account-name tier [@owner]",
        )
        return

    channel_id, channel_display_name, account_name, tier, owner_slack_user_id = parsed
    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to register: missing Slack workspace id.")
        return

    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()
            if workspace is None:
                await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
                return

        customer_team_id, is_ext_shared = await _fetch_channel_metadata(client, channel_id, slack_team_id)

        async with get_session(workspace_id=workspace.id) as session:
            owner_user = None
            if owner_slack_user_id:
                owner_user = await _get_or_create_user(session, workspace.id, owner_slack_user_id)

            registering_user = None
            if command.get("user_id"):
                registering_user = await _get_or_create_user(session, workspace.id, command["user_id"])

            account = await _get_or_create_account(
                session,
                workspace.id,
                account_name,
                tier,
                owner_user.id if owner_user else None,
            )
            channel = await register_channel(
                session=session,
                workspace_id=workspace.id,
                slack_channel_id=channel_id,
                account_id=account.id,
                registered_by_user_id=registering_user.id if registering_user else None,
            )
            channel.slack_channel_name = channel_display_name
            channel.customer_slack_team_id = customer_team_id
            channel.is_ext_shared = is_ext_shared
    except Exception as exc:
        logger.exception("register_failed team=%s channel=%s account=%r", slack_team_id, channel_id, account_name)
        await respond(response_type="ephemeral", text=f"Registration failed: {type(exc).__name__}")
        return

    await respond(
        response_type="ephemeral",
        text=f"Channel #{channel_display_name} registered for account '{account_name}' (tier: {tier}).",
    )
