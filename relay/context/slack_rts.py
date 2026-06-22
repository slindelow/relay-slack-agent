"""Slack Real-Time Search adapter for permission-aware internal context."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.context.contracts import ContextSource
from relay.crypto import decrypt_token, encrypt_token, ensure_workspace_dek, kms_provider_from_settings, workspace_encryption_key
from relay.db.models import User, UserSlackSearchToken, Workspace

logger = logging.getLogger(__name__)

PUBLIC_SEARCH_SCOPES = ("search:read.public", "search:read.files", "search:read.users")


class SlackSearchNotConnected(RuntimeError):
    """Raised when a user has not connected Slack search context."""


@dataclass(frozen=True)
class SlackSearchStatus:
    connected: bool
    scopes: str = ""
    connected_at: datetime | None = None


async def slack_search_status(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> SlackSearchStatus:
    result = await session.execute(
        select(UserSlackSearchToken)
        .where(
            UserSlackSearchToken.workspace_id == workspace_id,
            UserSlackSearchToken.slack_user_id == slack_user_id,
            UserSlackSearchToken.is_revoked.is_(False),
        )
        .order_by(UserSlackSearchToken.connected_at.desc())
    )
    token = result.scalar_one_or_none()
    if token is None:
        return SlackSearchStatus(connected=False)
    return SlackSearchStatus(
        connected=True,
        scopes=token.scopes,
        connected_at=token.connected_at,
    )


async def store_user_search_token(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    slack_user_id: str,
    access_token: str,
    scopes: str,
) -> UserSlackSearchToken:
    user_result = await session.execute(
        select(User).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == slack_user_id,
            User.deleted_at.is_(None),
        )
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        user = User(
            workspace_id=workspace_id,
            slack_user_id=slack_user_id,
            relay_role="viewer",
        )
        session.add(user)
        await session.flush()

    existing_result = await session.execute(
        select(UserSlackSearchToken).where(
            UserSlackSearchToken.workspace_id == workspace_id,
            UserSlackSearchToken.user_id == user.id,
            UserSlackSearchToken.is_revoked.is_(False),
        )
    )
    for existing in existing_result.scalars():
        existing.is_revoked = True
        existing.revoked_at = datetime.now(UTC)

    settings = get_settings()
    key = settings.token_encryption_key_bytes
    kms_provider = kms_provider_from_settings(settings)
    if kms_provider is not None:
        workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = workspace_result.scalar_one()
        key = ensure_workspace_dek(workspace, key, kms_provider)

    encrypted_access_token, nonce = encrypt_token(access_token, key)
    token = UserSlackSearchToken(
        workspace_id=workspace_id,
        user_id=user.id,
        slack_user_id=slack_user_id,
        encrypted_access_token=encrypted_access_token,
        encrypted_access_token_nonce=nonce,
        scopes=scopes,
    )
    session.add(token)
    await session.flush()
    return token


async def _load_user_search_token(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    slack_user_id: str,
) -> str:
    result = await session.execute(
        select(UserSlackSearchToken, Workspace)
        .join(Workspace, Workspace.id == UserSlackSearchToken.workspace_id)
        .where(
            UserSlackSearchToken.workspace_id == workspace_id,
            UserSlackSearchToken.slack_user_id == slack_user_id,
            UserSlackSearchToken.is_revoked.is_(False),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise SlackSearchNotConnected("Slack search context is not connected for this user")

    token_row, workspace = row
    settings = get_settings()
    key = settings.token_encryption_key_bytes
    kms_provider = kms_provider_from_settings(settings)
    if kms_provider is not None:
        key = workspace_encryption_key(workspace, key, kms_provider)
    return decrypt_token(
        token_row.encrypted_access_token,
        token_row.encrypted_access_token_nonce,
        key,
    )


class SlackRTSClient:
    """Thin wrapper around Slack's assistant.search.context API."""

    async def search_internal_context(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        acting_slack_user_id: str,
        query: str,
        top_k: int = 5,
        channel_filter: list[str] | None = None,
        exclude_channel_ids: set[str] | None = None,
    ) -> list[ContextSource]:
        if top_k <= 0 or not query.strip():
            return []

        user_token = await _load_user_search_token(
            session,
            workspace_id=workspace_id,
            slack_user_id=acting_slack_user_id,
        )
        payload: dict[str, Any] = {
            "query": query.strip(),
            "content_types": ["messages", "files"],
            "channel_types": ["public_channel"],
            "limit": min(top_k, 10),
        }
        if channel_filter:
            payload["channels"] = channel_filter

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://slack.com/api/assistant.search.context",
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            logger.info("slack_rts_search_failed workspace=%s error=%s", workspace_id, error)
            return []
        return _sources_from_rts_response(
            data,
            top_k=top_k,
            exclude_channel_ids=exclude_channel_ids,
        )


def _sources_from_rts_response(
    data: dict[str, Any],
    *,
    top_k: int,
    exclude_channel_ids: set[str] | None = None,
) -> list[ContextSource]:
    results = data.get("results") or {}
    raw_items: list[dict[str, Any]] = []
    if isinstance(results, list):
        raw_items = [item for item in results if isinstance(item, dict)]
    elif isinstance(results, dict):
        for key in ("messages", "files"):
            values = results.get(key) or []
            if isinstance(values, list):
                raw_items.extend(item for item in values if isinstance(item, dict))

    sources: list[ContextSource] = []
    excluded = exclude_channel_ids or set()
    for item in raw_items[:top_k]:
        channel_id = item.get("channel_id") or item.get("channel")
        if channel_id and str(channel_id) in excluded:
            continue
        title = (
            item.get("title")
            or item.get("channel_name")
            or item.get("name")
            or "Slack search result"
        )
        excerpt = (
            item.get("text")
            or item.get("snippet")
            or item.get("summary")
            or item.get("context")
            or ""
        )
        permalink = item.get("permalink") or item.get("url")
        ts_value = item.get("timestamp") or item.get("ts")
        freshness_ts = _parse_slack_ts(ts_value)
        sources.append(
            ContextSource(
                title=str(title),
                provider="slack_rts",
                url=str(permalink) if permalink else None,
                excerpt=str(excerpt)[:800],
                freshness_ts=freshness_ts,
                stale=False,
                visibility="internal",
            )
        )
    return [source for source in sources if source.excerpt.strip()]


def _parse_slack_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError):
        return None
