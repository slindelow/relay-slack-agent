from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from relay.context.slack_rts import _sources_from_rts_response, revoke_user_search_tokens, slack_search_status, store_user_search_token
from relay.crypto import decrypt_token
from relay.db.models import User, UserSlackSearchToken
from relay.slack.oauth import upsert_workspace_from_install


def test_sources_from_rts_response_marks_slack_results_internal():
    sources = _sources_from_rts_response(
        {
            "ok": True,
            "results": {
                "messages": [
                    {
                        "title": "support-internal",
                        "text": "We fixed this in the SSO cert runbook.",
                        "permalink": "https://example.slack.com/archives/C123/p1",
                        "ts": "1710000000.000100",
                    }
                ],
                "files": [
                    {
                        "title": "SSO checklist",
                        "snippet": "Certificate rotation checklist",
                        "permalink": "https://example.slack.com/files/F123",
                    }
                ],
            },
        },
        top_k=5,
    )

    assert [source.provider for source in sources] == ["slack_rts", "slack_rts"]
    assert {source.visibility for source in sources} == {"internal"}
    assert sources[0].url.startswith("https://example.slack.com/")


def test_sources_from_rts_response_excludes_registered_connect_channels():
    sources = _sources_from_rts_response(
        {
            "ok": True,
            "results": {
                "messages": [
                    {
                        "channel_id": "C_CONNECT",
                        "title": "customer-connect",
                        "text": "Customer-only context should not be returned.",
                    },
                    {
                        "channel_id": "C_INTERNAL",
                        "title": "support-internal",
                        "text": "Internal context is allowed.",
                    },
                ],
            },
        },
        top_k=5,
        exclude_channel_ids={"C_CONNECT"},
    )

    assert [source.title for source in sources] == ["support-internal"]


@pytest.mark.asyncio
async def test_store_user_search_token_encrypts_and_replaces_active_token(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_RTS", "RTS Corp")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )
    user = User(
        workspace_id=workspace.id,
        slack_user_id="U_RTS",
        relay_role="csm",
    )
    db_session.add(user)
    await db_session.flush()

    first = await store_user_search_token(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_RTS",
        access_token="xoxp-first",
        scopes="search:read.public",
    )
    second = await store_user_search_token(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_RTS",
        access_token="xoxp-second",
        scopes="search:read.public,search:read.files",
    )

    assert first.is_revoked is True
    assert second.is_revoked is False
    assert decrypt_token(
        second.encrypted_access_token,
        second.encrypted_access_token_nonce,
        relay_settings.token_encryption_key_bytes,
    ) == "xoxp-second"

    status = await slack_search_status(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_RTS",
    )
    assert status.connected is True
    assert "search:read.files" in status.scopes

    rows = await db_session.execute(
        select(UserSlackSearchToken).where(UserSlackSearchToken.workspace_id == workspace.id)
    )
    assert len(list(rows.scalars())) == 2


@pytest.mark.asyncio
async def test_revoke_user_search_tokens_marks_active_token_revoked(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_REVOKE", "Revoke Corp")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )

    await store_user_search_token(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_REVOKE",
        access_token="xoxp-revoke-token",
        scopes="search:read.public",
    )
    await db_session.flush()

    # Confirm it exists and is active
    result = await db_session.execute(
        select(UserSlackSearchToken).where(
            UserSlackSearchToken.workspace_id == workspace.id,
            UserSlackSearchToken.slack_user_id == "U_REVOKE",
            UserSlackSearchToken.is_revoked.is_(False),
        )
    )
    assert result.scalar_one_or_none() is not None

    # Revoke
    await revoke_user_search_tokens(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_REVOKE",
    )
    await db_session.flush()

    # Confirm it is now revoked
    result = await db_session.execute(
        select(UserSlackSearchToken).where(
            UserSlackSearchToken.workspace_id == workspace.id,
            UserSlackSearchToken.slack_user_id == "U_REVOKE",
            UserSlackSearchToken.is_revoked.is_(False),
        )
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_revoke_user_search_tokens_noop_when_no_tokens(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(db_session, "T_NOOP", "NoToken Corp")
    await db_session.flush()
    await db_session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace.id)},
    )
    # Should not raise even if there are no tokens to revoke
    await revoke_user_search_tokens(
        db_session,
        workspace_id=workspace.id,
        slack_user_id="U_NO_TOKENS",
    )
