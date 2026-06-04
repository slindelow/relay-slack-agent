"""Workspace install lifecycle helpers."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.crypto import encrypt_token
from relay.db.models import SlaPolicy, Workspace, WorkspaceSettings, WorkspaceToken


async def _set_workspace_context(session: AsyncSession, workspace_id: uuid.UUID) -> None:
    await session.execute(
        text("SET LOCAL app.current_workspace_id = :workspace_id"),
        {"workspace_id": str(workspace_id)},
    )


async def upsert_workspace_from_install(
    session: AsyncSession,
    slack_team_id: str,
    slack_team_name: str,
) -> Workspace:
    result = await session.execute(select(Workspace).where(Workspace.slack_team_id == slack_team_id))
    workspace = result.scalar_one_or_none()

    if workspace is None:
        workspace = Workspace(slack_team_id=slack_team_id, slack_team_name=slack_team_name)
        session.add(workspace)
        await session.flush()
        await _set_workspace_context(session, workspace.id)
        session.add(WorkspaceSettings(workspace_id=workspace.id))
        for tier, response_min, escalation_min in (
            ("enterprise", 30, 45),
            ("pro", 120, 180),
            ("starter", 480, 600),
        ):
            session.add(
                SlaPolicy(
                    workspace_id=workspace.id,
                    tier_name=tier,
                    response_window_minutes=response_min,
                    escalation_window_minutes=escalation_min,
                )
            )
    else:
        await _set_workspace_context(session, workspace.id)
        workspace.slack_team_name = slack_team_name
        workspace.uninstalled_at = None
        workspace.installed_at = datetime.now(timezone.utc)

    return workspace


async def store_bot_token(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    bot_token: str,
    scopes: str,
) -> WorkspaceToken:
    settings = get_settings()
    await _set_workspace_context(session, workspace_id)
    existing = await session.execute(
        select(WorkspaceToken).where(
            WorkspaceToken.workspace_id == workspace_id,
            WorkspaceToken.token_type == "bot",
            WorkspaceToken.is_revoked.is_(False),
        )
    )
    for old_token in existing.scalars():
        old_token.is_revoked = True
        old_token.revoked_at = datetime.now(timezone.utc)

    ciphertext, nonce = encrypt_token(bot_token, settings.token_encryption_key_bytes)
    token = WorkspaceToken(
        workspace_id=workspace_id,
        token_type="bot",
        encrypted_token=ciphertext,
        encrypted_token_nonce=nonce,
        scopes=scopes,
    )
    session.add(token)
    return token
