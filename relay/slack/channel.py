"""Channel registration helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.models import MonitoredChannel


class ChannelNotRegisteredError(Exception):
    """Raised when operating on a channel that has not been registered."""


async def register_channel(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_channel_id: str,
    account_id: uuid.UUID,
    registered_by_user_id: uuid.UUID | None = None,
) -> MonitoredChannel:
    """Upsert a MonitoredChannel record.

    - If a record with (workspace_id, slack_channel_id) already exists,
      set is_active=True, update account_id, and return it.
    - Otherwise create a new MonitoredChannel with is_active=True.

    Does NOT call the Slack API and does NOT commit — the caller is
    responsible for committing the session.
    """
    result = await session.execute(
        select(MonitoredChannel).where(
            MonitoredChannel.workspace_id == workspace_id,
            MonitoredChannel.slack_channel_id == slack_channel_id,
        )
    )
    existing = result.scalars().first()

    if existing is not None:
        existing.is_active = True
        existing.account_id = account_id
        return existing

    channel = MonitoredChannel(
        workspace_id=workspace_id,
        slack_channel_id=slack_channel_id,
        account_id=account_id,
        registered_by_user_id=registered_by_user_id,
        is_active=True,
    )
    session.add(channel)
    return channel


async def set_channel_customer_team(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_channel_id: str,
    customer_slack_team_id: str | None,
    is_ext_shared: bool = False,
) -> MonitoredChannel:
    """Update the customer team metadata on a registered channel.

    Raises ChannelNotRegisteredError if the channel is not found.
    """
    result = await session.execute(
        select(MonitoredChannel).where(
            MonitoredChannel.workspace_id == workspace_id,
            MonitoredChannel.slack_channel_id == slack_channel_id,
        )
    )
    channel = result.scalars().first()

    if channel is None:
        raise ChannelNotRegisteredError(
            f"Channel {slack_channel_id} is not registered for workspace {workspace_id}"
        )

    channel.customer_slack_team_id = customer_slack_team_id
    channel.is_ext_shared = is_ext_shared
    return channel
