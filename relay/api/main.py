"""FastAPI app mounting Slack Bolt."""

import logging
import secrets
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from relay.config import get_settings
from relay.crypto import encrypt_token
from relay.integrations.hubspot import HubSpotOAuthError, exchange_code_for_tokens, hubspot_oauth_url
from relay.slack.app import app as bolt_app

logger = logging.getLogger(__name__)

api = FastAPI(title="RELAY", version="0.1.0")
handler = AsyncSlackRequestHandler(bolt_app)


@api.get("/health")
async def health():
    return {"status": "ok", "service": "relay"}


@api.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@api.get("/slack/install")
async def slack_install(req: Request):
    return await handler.handle(req)


@api.get("/slack/oauth_redirect")
async def slack_oauth_redirect(req: Request):
    return await handler.handle(req)


@api.get("/hubspot/install")
async def hubspot_install(req: Request):
    """Redirect admin to HubSpot OAuth authorization page."""
    settings = get_settings()
    # Use workspace_id from query param as state if provided, else random
    state = req.query_params.get("workspace_id") or secrets.token_urlsafe(16)
    url = hubspot_oauth_url(
        client_id=settings.hubspot_client_id,
        redirect_uri=settings.hubspot_redirect_uri,
        state=state,
    )
    return RedirectResponse(url=url, status_code=302)


@api.get("/hubspot/oauth_redirect")
async def hubspot_oauth_redirect(
    req: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Receive HubSpot OAuth redirect, exchange code for tokens, store in DB."""
    if error:
        return JSONResponse({"error": error}, status_code=400)

    # Validate state as workspace_id (UUID)
    if not state:
        return JSONResponse({"error": "missing state parameter"}, status_code=400)
    try:
        workspace_uuid = uuid.UUID(state)
    except ValueError:
        return JSONResponse(
            {"error": "invalid state — expected a workspace UUID"}, status_code=400
        )

    settings = get_settings()

    # Exchange code for tokens
    try:
        token_data = await exchange_code_for_tokens(
            code=code,
            client_id=settings.hubspot_client_id,
            client_secret=settings.hubspot_client_secret,
            redirect_uri=settings.hubspot_redirect_uri,
        )
    except HubSpotOAuthError as exc:
        logger.error("HubSpot token exchange failed: %s", exc)
        return JSONResponse({"error": "token_exchange_failed", "detail": str(exc)}, status_code=502)
    except Exception as exc:
        logger.exception("Unexpected error during HubSpot token exchange: %s", exc)
        return JSONResponse({"error": "internal_error"}, status_code=500)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    # Encrypt tokens
    key = settings.token_encryption_key_bytes
    enc_access, nonce_access = encrypt_token(access_token, key)
    enc_refresh, nonce_refresh = encrypt_token(refresh_token, key) if refresh_token else (None, None)

    # Upsert CrmConnection
    try:
        from sqlalchemy import select
        from datetime import datetime, timezone

        from relay.db.models import CrmConnection
        from relay.db.session import get_session

        async with get_session(workspace_id=workspace_uuid) as session:
            stmt = select(CrmConnection).where(
                CrmConnection.workspace_id == workspace_uuid,
                CrmConnection.crm_provider == "hubspot",
            )
            result = await session.execute(stmt)
            connection = result.scalar_one_or_none()

            now = datetime.now(tz=timezone.utc)
            if connection is None:
                connection = CrmConnection(
                    workspace_id=workspace_uuid,
                    crm_provider="hubspot",
                    encrypted_access_token=enc_access,
                    encrypted_access_token_nonce=nonce_access,
                    encrypted_refresh_token=enc_refresh,
                    encrypted_refresh_token_nonce=nonce_refresh,
                    connected_at=now,
                    sync_status="not_synced",
                    disconnected_at=None,
                )
                session.add(connection)
            else:
                connection.encrypted_access_token = enc_access
                connection.encrypted_access_token_nonce = nonce_access
                connection.encrypted_refresh_token = enc_refresh
                connection.encrypted_refresh_token_nonce = nonce_refresh
                connection.connected_at = now
                connection.sync_status = "not_synced"
                connection.disconnected_at = None
    except Exception as exc:
        logger.exception("Failed to store HubSpot connection for workspace_id=%s: %s", workspace_uuid, exc)
        return JSONResponse({"error": "db_error", "detail": str(exc)}, status_code=500)

    # Enqueue sync task
    try:
        from relay.worker.hubspot_tasks import sync_hubspot_accounts

        sync_hubspot_accounts.delay(str(workspace_uuid))
    except Exception as exc:
        logger.warning("Failed to enqueue sync_hubspot_accounts: %s", exc)
        # Non-fatal — connection is stored, sync can be triggered later

    return JSONResponse({"status": "connected"})

