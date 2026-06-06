"""FastAPI app mounting Slack Bolt."""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from sqlalchemy import select

from relay.config import get_settings
from relay.db.models import FeedbackSignal, User, Workspace
from relay.db.session import get_session
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


async def _slack_auth_test(token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=503, detail="Slack API unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="Slack API unavailable")
    data = response.json()
    if not data.get("ok"):
        raise HTTPException(status_code=401, detail="Invalid Slack token")
    return data


def _feedback_signal_to_json(row: FeedbackSignal) -> str:
    payload = {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "actor_user_id": row.actor_user_id,
        "question_id": str(row.question_id) if row.question_id else None,
        "draft_id": str(row.draft_id) if row.draft_id else None,
        "message_id": str(row.message_id) if row.message_id else None,
        "correction_action": row.correction_action,
        "original_label": row.original_label,
        "corrected_label": row.corrected_label,
        "original_confidence": row.original_confidence,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    return json.dumps(payload, separators=(",", ":")) + "\n"


@api.get("/relay/admin/feedback-export")
async def feedback_export(
    authorization: str = Header(default=""),
    days: int = Query(default=7, ge=1, le=90),
):
    """Export workspace-scoped feedback signals as JSONL for classifier review."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    auth = await _slack_auth_test(token)
    slack_team_id = auth.get("team_id")
    slack_user_id = auth.get("user_id")
    if not slack_team_id or not slack_user_id:
        raise HTTPException(status_code=401, detail="Slack auth.test did not return team/user")

    async with get_session() as session:
        workspace_result = await session.execute(
            select(Workspace).where(Workspace.slack_team_id == slack_team_id)
        )
        workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")

    since = datetime.now(UTC) - timedelta(days=days)

    async with get_session(workspace.id) as session:
        user_result = await session.execute(
            select(User).where(
                User.workspace_id == workspace.id,
                User.slack_user_id == slack_user_id,
            )
        )
        user = user_result.scalar_one_or_none()
        if user is None or user.relay_role != "admin":
            raise HTTPException(status_code=403, detail="admin role required")

        feedback_result = await session.execute(
            select(FeedbackSignal)
            .where(
                FeedbackSignal.workspace_id == workspace.id,
                FeedbackSignal.created_at >= since,
            )
            .order_by(FeedbackSignal.created_at.asc())
        )
        rows = list(feedback_result.scalars())

    date_str = datetime.now(UTC).date().isoformat()
    content = "\n".join(r.rstrip("\n") for r in (_feedback_signal_to_json(r) for r in rows))
    if content:
        content += "\n"
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="relay-feedback-{date_str}.jsonl"'},
    )


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
