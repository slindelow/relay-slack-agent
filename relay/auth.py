"""Authorization helpers for RELAY slash-command and action handlers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.models import User


async def require_relay_admin(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> bool:
    """Return True if the Slack user has relay_role='admin' in this workspace."""
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
            User.relay_role == "admin",
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def require_relay_csm(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> bool:
    """Return True if the Slack user has relay_role in ('admin', 'csm')."""
    result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
            User.relay_role.in_(["admin", "csm"]),
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None
