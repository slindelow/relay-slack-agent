"""Database-backed Slack OAuth installation store."""

from __future__ import annotations

import logging
from typing import Optional

from slack_sdk.oauth.installation_store import Bot, Installation
from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from sqlalchemy import select, text

from relay.config import get_settings
from relay.crypto import decrypt_token, kms_provider_from_settings, workspace_encryption_key
from relay.db.models import Workspace, WorkspaceToken
from relay.db.session import get_session
from relay.slack.oauth import bootstrap_first_admin, store_bot_token, upsert_workspace_from_install

logger = logging.getLogger(__name__)


class DBInstallationStore(AsyncInstallationStore):
    """Slack installation store backed by PostgreSQL.

    Bolt calls async_save() after a successful OAuth install and async_find_bot()
    on every inbound event/command to retrieve the workspace bot token.
    """

    async def async_save(self, installation: Installation) -> None:
        team_id = installation.team_id or ""
        team_name = installation.team_name or team_id
        bot_token = installation.bot_token or ""
        bot_scopes = ",".join(installation.bot_scopes or [])
        installer_user_id = installation.user_id or ""

        async with get_session() as session:
            workspace = await upsert_workspace_from_install(session, team_id, team_name)
            await store_bot_token(session, workspace.id, bot_token, bot_scopes)
            if installer_user_id:
                await bootstrap_first_admin(session, workspace.id, installer_user_id)

        logger.info("installation_saved team=%s installer=%s", team_id, installer_user_id)

    async def async_find_bot(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Bot]:
        if not team_id:
            return None

        settings = get_settings()
        kms = kms_provider_from_settings(settings)

        try:
            async with get_session() as session:
                ws_result = await session.execute(
                    select(Workspace).where(
                        Workspace.slack_team_id == team_id,
                        Workspace.deleted_at.is_(None),
                    )
                )
                workspace = ws_result.scalar_one_or_none()
                if workspace is None:
                    return None

                await session.execute(
                    text("SELECT set_config('app.current_workspace_id', :wid, true)"),
                    {"wid": str(workspace.id)},
                )

                tok_result = await session.execute(
                    select(WorkspaceToken).where(
                        WorkspaceToken.workspace_id == workspace.id,
                        WorkspaceToken.token_type == "bot",
                        WorkspaceToken.is_revoked.is_(False),
                    )
                )
                token_row = tok_result.scalar_one_or_none()
                if token_row is None:
                    return None

                key = settings.token_encryption_key_bytes
                if kms is not None:
                    key = workspace_encryption_key(workspace, key, kms)

                bot_token = decrypt_token(
                    token_row.encrypted_token,
                    token_row.encrypted_token_nonce,
                    key,
                )

            return Bot(
                team_id=team_id,
                team_name=workspace.slack_team_name,
                enterprise_id=enterprise_id or "",
                bot_id="",
                bot_user_id="",
                bot_token=bot_token,
                bot_scopes=(token_row.scopes or "").split(",") if token_row.scopes else [],
                is_enterprise_install=is_enterprise_install or False,
                installed_at=workspace.installed_at,
            )
        except Exception:
            logger.exception("find_bot_failed team=%s", team_id)
            return None

    async def async_delete_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
    ) -> None:
        # Token revocation is handled by the app_uninstalled Slack event handler.
        pass
