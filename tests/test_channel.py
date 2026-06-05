"""Unit tests for channel registration helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from relay.db.models import MonitoredChannel
from relay.slack.channel import (
    ChannelNotRegisteredError,
    register_channel,
    set_channel_customer_team,
)


def _make_channel(**kwargs) -> MonitoredChannel:
    """Build a minimal MonitoredChannel instance without a DB session."""
    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        slack_channel_id="C12345",
        is_active=True,
        is_ext_shared=False,
        customer_slack_team_id=None,
        registered_by_user_id=None,
    )
    defaults.update(kwargs)
    return MonitoredChannel(**defaults)


def _mock_session_with(result_obj):
    """Return an AsyncMock session whose execute() returns a scalar result_obj."""
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = result_obj
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    # session.add is synchronous in SQLAlchemy's AsyncSession
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_register_channel_creates_new():
    """When no existing channel is found, a new MonitoredChannel is created."""
    workspace_id = uuid.uuid4()
    account_id = uuid.uuid4()
    session = _mock_session_with(None)  # no existing record

    channel = await register_channel(
        session=session,
        workspace_id=workspace_id,
        slack_channel_id="C99999",
        account_id=account_id,
    )

    assert isinstance(channel, MonitoredChannel)
    assert channel.workspace_id == workspace_id
    assert channel.slack_channel_id == "C99999"
    assert channel.account_id == account_id
    assert channel.is_active is True
    session.add.assert_called_once_with(channel)


@pytest.mark.asyncio
async def test_register_channel_reactivates_existing():
    """When a channel already exists, is_active is set to True and account_id updated."""
    workspace_id = uuid.uuid4()
    new_account_id = uuid.uuid4()
    existing = _make_channel(
        workspace_id=workspace_id,
        slack_channel_id="C12345",
        is_active=False,
    )
    session = _mock_session_with(existing)

    result = await register_channel(
        session=session,
        workspace_id=workspace_id,
        slack_channel_id="C12345",
        account_id=new_account_id,
    )

    assert result is existing
    assert existing.is_active is True
    assert existing.account_id == new_account_id
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_set_channel_customer_team_updates_fields():
    """When the channel exists, customer_slack_team_id and is_ext_shared are updated."""
    workspace_id = uuid.uuid4()
    existing = _make_channel(
        workspace_id=workspace_id,
        slack_channel_id="C12345",
        customer_slack_team_id=None,
        is_ext_shared=False,
    )
    session = _mock_session_with(existing)

    result = await set_channel_customer_team(
        session=session,
        workspace_id=workspace_id,
        slack_channel_id="C12345",
        customer_slack_team_id="T_CUSTOMER",
        is_ext_shared=True,
    )

    assert result is existing
    assert existing.customer_slack_team_id == "T_CUSTOMER"
    assert existing.is_ext_shared is True


@pytest.mark.asyncio
async def test_set_channel_customer_team_raises_when_not_found():
    """ChannelNotRegisteredError is raised when the channel does not exist."""
    session = _mock_session_with(None)

    with pytest.raises(ChannelNotRegisteredError):
        await set_channel_customer_team(
            session=session,
            workspace_id=uuid.uuid4(),
            slack_channel_id="C_MISSING",
            customer_slack_team_id="T_CUSTOMER",
        )
