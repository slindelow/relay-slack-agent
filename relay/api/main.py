"""FastAPI app mounting Slack Bolt."""

import logging
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from relay.config import get_settings
from relay.integrations.hubspot import (
    HubSpotOAuthError,
    build_hubspot_state,
    exchange_code_for_tokens,
    hubspot_oauth_url,
    parse_hubspot_state,
    store_hubspot_connection,
)
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
    workspace_id = req.query_params.get("workspace_id")
    if not workspace_id:
        return JSONResponse({"error": "missing workspace_id"}, status_code=400)
    try:
        state = build_hubspot_state(
            workspace_id=UUID(workspace_id),
            signing_key=settings.token_encryption_key_bytes,
        )
    except ValueError:
        return JSONResponse({"error": "invalid workspace_id"}, status_code=400)
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
        workspace_uuid = parse_hubspot_state(
            state,
            signing_key=get_settings().token_encryption_key_bytes,
        )
    except (HubSpotOAuthError, ValueError, KeyError):
        return JSONResponse({"error": "invalid state"}, status_code=400)

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

    # Upsert CrmConnection
    try:
        from relay.db.session import get_session

        async with get_session(workspace_id=workspace_uuid) as session:
            await store_hubspot_connection(session, workspace_uuid, token_data)
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
