"""Workspace install lifecycle helpers."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.crypto import encrypt_token, ensure_workspace_dek, kms_provider_from_settings
from relay.db.models import SlaPolicy, User, Workspace, WorkspaceSettings, WorkspaceToken

logger = logging.getLogger(__name__)


async def _set_workspace_context(session: AsyncSession, workspace_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
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


async def bootstrap_first_admin(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    installer_slack_user_id: str,
) -> None:
    """Promote the installing user to admin if no admin exists yet for this workspace."""
    count_result = await session.execute(
        select(func.count()).select_from(User).where(
            User.workspace_id == workspace_id,
            User.relay_role == "admin",
            User.deleted_at.is_(None),
        )
    )
    if (count_result.scalar_one() or 0) > 0:
        return

    user_result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == installer_slack_user_id,
        )
    )
    user = user_result.scalar_one_or_none()
    if user is not None:
        user.relay_role = "admin"
    else:
        session.add(User(
            workspace_id=workspace_id,
            slack_user_id=installer_slack_user_id,
            relay_role="admin",
        ))
    logger.info("bootstrap_first_admin workspace=%s user=%s", workspace_id, installer_slack_user_id)


async def store_bot_token(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    bot_token: str,
    scopes: str,
) -> WorkspaceToken:
    settings = get_settings()
    await _set_workspace_context(session, workspace_id)
    kms_provider = kms_provider_from_settings(settings)
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

    key = settings.token_encryption_key_bytes
    if kms_provider is not None:
        workspace_result = await session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = workspace_result.scalar_one()
        key = ensure_workspace_dek(workspace, key, kms_provider)
    ciphertext, nonce = encrypt_token(bot_token, key)
    token = WorkspaceToken(
        workspace_id=workspace_id,
        token_type="bot",
        encrypted_token=ciphertext,
        encrypted_token_nonce=nonce,
        scopes=scopes,
    )
    session.add(token)
    return token
