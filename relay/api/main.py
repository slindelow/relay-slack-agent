"""FastAPI app mounting Slack Bolt."""

import json
import logging
import hmac
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from sqlalchemy import select, text, update

from relay.config import get_settings
from relay.db.engine import get_engine
from relay.db.models import (
    Assignment,
    AuditLog,
    CustomerAccount,
    Draft,
    FeedbackSignal,
    Message,
    MonitoredChannel,
    QuestionEvent,
    Snooze,
    User,
    Workspace,
)
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

settings = get_settings()
if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.0,
    )

api = FastAPI(title="RELAY", version="0.1.0")
handler = AsyncSlackRequestHandler(bolt_app)


async def _check_db() -> str:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("health_db_check_failed")
        return "error"


async def _check_redis() -> str:
    try:
        import redis.asyncio as redis

        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return "ok"
    except Exception:
        logger.exception("health_redis_check_failed")
        return "error"


@api.get("/health")
async def health():
    db_status = await _check_db()
    redis_status = await _check_redis()
    status = "ok" if db_status == "ok" and redis_status == "ok" else "error"
    body = {"status": status, "service": "relay", "db": db_status, "redis": redis_status}
    if status != "ok":
        return JSONResponse(body, status_code=503)
    return body


def _html_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | RELAY</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: #17202a; }}
    main {{ max-width: 840px; margin: 0 auto; padding: 48px 24px 72px; }}
    h1, h2 {{ line-height: 1.2; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""
    )


@api.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return _html_page(
        "Privacy Policy",
        """
<h1>RELAY Privacy Policy</h1>
<p>RELAY helps customer success teams monitor Slack Connect customer channels, detect unanswered questions, retrieve approved context, and draft responses for human approval.</p>
<h2>Data We Collect</h2>
<ul>
  <li>Slack workspace identifiers, user identifiers, channel identifiers, and installation metadata.</li>
  <li>Short message excerpts and question metadata from registered Slack Connect channels only.</li>
  <li>Customer account metadata such as tier, ARR, renewal date, health score, and owner assignment when connected from CRM systems.</li>
  <li>Drafts, approval metadata, feedback signals, impact metrics, and retrieval logs needed to operate and improve RELAY.</li>
  <li>Optional connector content from administrator-configured knowledge sources such as Google Drive and GitHub.</li>
</ul>
<h2>Retention</h2>
<p>Raw Slack excerpts are retained for up to 90 days. Operational metadata, drafts, feedback, retrieval logs, and impact metrics are retained for up to one year unless a workspace admin requests deletion earlier. Connector-derived content is removed when the connector is disconnected and purged.</p>
<h2>Sub-processors</h2>
<p>RELAY uses Anthropic for LLM processing with no-training/ZDR settings where available, an embedding provider for semantic retrieval, the selected cloud hosting provider, and Sentry for production error monitoring. See <a href="/sub-processors">Sub-processors</a>.</p>
<h2>User Rights and Deletion</h2>
<p>Workspace admins can request deletion through <code>/relay delete-workspace-data</code> once enabled or by contacting privacy@relay.example.com. Individual user erasure requests can be sent to the same address.</p>
<h2>Contact</h2>
<p>Privacy and DPA requests: privacy@relay.example.com.</p>
""",
    )


@api.get("/terms", response_class=HTMLResponse)
async def terms():
    return _html_page(
        "Terms of Service",
        """
<h1>RELAY Terms of Service</h1>
<p>These terms govern use of RELAY, a Slack-native assistant for customer success teams. By installing or using RELAY, your organization agrees to use the service only for lawful business purposes and only in workspaces and channels where it has the right to process the relevant data.</p>
<h2>Human Approval</h2>
<p>RELAY drafts customer responses but does not send generated responses without human approval. Your organization is responsible for reviewing messages before they are posted.</p>
<h2>Accounts and Access</h2>
<p>Workspace administrators control installation, source connectors, user roles, and deletion requests. You are responsible for maintaining appropriate Slack and connector permissions.</p>
<h2>Service Availability</h2>
<p>RELAY is provided on a commercially reasonable basis. Beta and pilot deployments may change as Marketplace readiness work is completed.</p>
<h2>Contact</h2>
<p>Questions about these terms: legal@relay.example.com.</p>
""",
    )


@api.get("/sub-processors", response_class=HTMLResponse)
async def sub_processors():
    return _html_page(
        "Sub-processors",
        """
<h1>RELAY Sub-processors</h1>
<table>
  <thead><tr><th>Name</th><th>Service</th><th>Data Sent</th><th>Region</th><th>DPA</th></tr></thead>
  <tbody>
    <tr><td>Anthropic</td><td>LLM draft and summary generation</td><td>Question excerpts, retrieved evidence, account context needed for a draft</td><td>United States</td><td>Available from Anthropic</td></tr>
    <tr><td>Embedding provider</td><td>Semantic embeddings</td><td>Connector chunks and approved Q+A text</td><td>United States</td><td>Provider DPA</td></tr>
    <tr><td>Cloud hosting provider</td><td>Application hosting, database, queue</td><td>Application data stored by RELAY</td><td>United States</td><td>Provider DPA</td></tr>
    <tr><td>Sentry</td><td>Error monitoring</td><td>Error traces and operational metadata; no intentional message content</td><td>United States</td><td>Available from Sentry</td></tr>
  </tbody>
</table>
""",
    )


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
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
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


def build_confirmation_token(workspace_id: UUID, slack_user_id: str, signing_key: bytes) -> str:
    message = f"{workspace_id}:{slack_user_id}".encode()
    return hmac.new(signing_key, message, hashlib.sha256).hexdigest()


def _verify_confirmation_token(workspace_id: UUID, slack_user_id: str, token: str) -> bool:
    expected = build_confirmation_token(
        workspace_id,
        slack_user_id,
        get_settings().token_encryption_key_bytes,
    )
    return hmac.compare_digest(expected, token)


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


@api.delete("/relay/admin/users/{slack_user_id}/erase")
async def erase_user(
    slack_user_id: str,
    req: Request,
    authorization: str = Header(default=""),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    body = await req.json()
    confirmation_token = body.get("confirmation_token", "")

    auth = await _slack_auth_test(authorization.removeprefix("Bearer ").strip())
    slack_team_id = auth.get("team_id")
    admin_slack_user_id = auth.get("user_id")
    if not slack_team_id or not admin_slack_user_id:
        raise HTTPException(status_code=401, detail="Slack auth.test did not return team/user")

    async with get_session() as session:
        workspace_result = await session.execute(
            select(Workspace).where(Workspace.slack_team_id == slack_team_id)
        )
        workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")

    if not _verify_confirmation_token(workspace.id, slack_user_id, confirmation_token):
        raise HTTPException(status_code=403, detail="invalid confirmation token")

    async with get_session(workspace.id) as session:
        admin_result = await session.execute(
            select(User).where(
                User.workspace_id == workspace.id,
                User.slack_user_id == admin_slack_user_id,
            )
        )
        admin = admin_result.scalar_one_or_none()
        if admin is None or admin.relay_role != "admin":
            raise HTTPException(status_code=403, detail="admin role required")

        user_result = await session.execute(
            select(User).where(
                User.workspace_id == workspace.id,
                User.slack_user_id == slack_user_id,
            )
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        user.display_name = None
        user.email = None
        user.deleted_at = datetime.now(UTC)

        await session.execute(
            update(AuditLog)
            .where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.actor_slack_user_id == slack_user_id,
            )
            .values(actor_slack_user_id=None, actor_user_id=None)
        )
        await session.execute(
            update(AuditLog)
            .where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.actor_user_id == user.id,
            )
            .values(actor_user_id=None, actor_slack_user_id=None)
        )
        await session.execute(
            update(QuestionEvent)
            .where(
                QuestionEvent.workspace_id == workspace.id,
                QuestionEvent.actor_user_id == user.id,
            )
            .values(actor_user_id=None)
        )
        await session.execute(
            update(FeedbackSignal)
            .where(
                FeedbackSignal.workspace_id == workspace.id,
                FeedbackSignal.actor_user_id == user.id,
            )
            .values(actor_user_id=None)
        )
        await session.execute(
            update(Draft)
            .where(
                Draft.workspace_id == workspace.id,
                Draft.editor_user_id == user.id,
            )
            .values(editor_user_id=None)
        )
        await session.execute(
            update(Draft)
            .where(
                Draft.workspace_id == workspace.id,
                Draft.approved_by_user_id == user.id,
            )
            .values(approved_by_user_id=None)
        )
        await session.execute(
            update(Snooze)
            .where(
                Snooze.workspace_id == workspace.id,
                Snooze.snoozed_by_user_id == user.id,
            )
            .values(snoozed_by_user_id=None)
        )
        await session.execute(
            update(Assignment)
            .where(
                Assignment.workspace_id == workspace.id,
                Assignment.assigned_by_user_id == user.id,
            )
            .values(assigned_by_user_id=None)
        )
        await session.execute(
            update(CustomerAccount)
            .where(
                CustomerAccount.workspace_id == workspace.id,
                CustomerAccount.owner_user_id == user.id,
            )
            .values(owner_user_id=None)
        )
        await session.execute(
            update(CustomerAccount)
            .where(
                CustomerAccount.workspace_id == workspace.id,
                CustomerAccount.backup_owner_user_id == user.id,
            )
            .values(backup_owner_user_id=None)
        )
        await session.execute(
            update(MonitoredChannel)
            .where(
                MonitoredChannel.workspace_id == workspace.id,
                MonitoredChannel.registered_by_user_id == user.id,
            )
            .values(registered_by_user_id=None)
        )
        await session.execute(
            update(Message)
            .where(
                Message.workspace_id == workspace.id,
                Message.sender_slack_user_id == slack_user_id,
            )
            .values(sender_slack_user_id=None)
        )
        session.add(
            AuditLog(
                workspace_id=workspace.id,
                actor_user_id=admin.id,
                actor_slack_user_id=admin.slack_user_id,
                event_type="user_erased",
                entity_type="user",
                entity_id=user.id,
            )
        )

    return {"erased": True, "user_id": str(user.id)}


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
