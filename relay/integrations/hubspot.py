"""HubSpot OAuth flow and account sync."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import UUID

import httpx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from relay.db.models import CrmConnection

HUBSPOT_AUTH_BASE = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_COMPANIES_URL = "https://api.hubapi.com/crm/v3/objects/companies"

HUBSPOT_SCOPES = (
    "crm.objects.companies.read"
    " crm.objects.contacts.read"
    " crm.objects.deals.read"
)


class HubSpotOAuthError(Exception):
    pass


class HubSpotAPIError(Exception):
    pass


def build_hubspot_state(
    workspace_id: UUID,
    signing_key: bytes,
    *,
    now: datetime | None = None,
) -> str:
    """Build a signed OAuth state token containing the workspace id."""
    issued_at = int((now or datetime.now(timezone.utc)).timestamp())
    payload = {
        "workspace_id": str(workspace_id),
        "nonce": secrets.token_urlsafe(16),
        "iat": issued_at,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(signing_key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_b64}.{signature_b64}"


def parse_hubspot_state(
    state: str,
    signing_key: bytes,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 600,
) -> UUID:
    """Validate a HubSpot OAuth state token and return its workspace id."""
    try:
        payload_b64, signature_b64 = state.split(".", 1)
        expected = hmac.new(signing_key, payload_b64.encode("ascii"), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
        if not hmac.compare_digest(expected, actual):
            raise HubSpotOAuthError("Invalid OAuth state signature")

        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(payload_bytes)
        issued_at = int(payload["iat"])
        current_time = int((now or datetime.now(timezone.utc)).timestamp())
        if issued_at > current_time + 60:
            raise HubSpotOAuthError("OAuth state issued in the future")
        if current_time - issued_at > max_age_seconds:
            raise HubSpotOAuthError("OAuth state expired")
        return UUID(payload["workspace_id"])
    except (ValueError, KeyError, json.JSONDecodeError, binascii.Error) as exc:
        raise HubSpotOAuthError("Invalid OAuth state format") from exc


def hubspot_oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Return HubSpot OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": HUBSPOT_SCOPES,
        "state": state,
    }
    return f"{HUBSPOT_AUTH_BASE}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    _client = client or httpx.AsyncClient()
    try:
        response = await _client.post(HUBSPOT_TOKEN_URL, data=data)
    finally:
        if client is None:
            await _client.aclose()

    if response.status_code != 200:
        raise HubSpotOAuthError(
            f"Token exchange failed: {response.status_code} [body redacted]"
        )
    return response.json()


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Refresh an expired access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    _client = client or httpx.AsyncClient()
    try:
        response = await _client.post(HUBSPOT_TOKEN_URL, data=data)
    finally:
        if client is None:
            await _client.aclose()

    if response.status_code != 200:
        raise HubSpotOAuthError(
            f"Token refresh failed: {response.status_code} [body redacted]"
        )
    return response.json()


async def fetch_hubspot_companies(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = 100,
    max_pages: int = 50,
) -> list[dict]:
    """Fetch all company objects from HubSpot CRM API, following pagination.

    HubSpot returns up to ``limit`` (max 100) companies per page plus a
    ``paging.next.after`` cursor when more remain. We follow the cursor until it
    is exhausted, so workspaces with more than 100 companies sync fully.
    ``max_pages`` is a safety cap against an unbounded loop (50 pages = 5000
    companies at the default page size).
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    _client = client or httpx.AsyncClient()
    results: list[dict] = []
    after: str | None = None
    try:
        for _ in range(max_pages):
            params = {
                "limit": limit,
                "properties": "name,domain,hs_lead_status,dealtype,createdate,hs_analytics_source,annualrevenue",
            }
            if after:
                params["after"] = after
            response = await _client.get(
                HUBSPOT_COMPANIES_URL,
                params=params,
                headers=headers,
            )
            if response.status_code != 200:
                raise HubSpotAPIError(
                    f"Companies fetch failed: {response.status_code} [body redacted]"
                )
            payload = response.json()
            results.extend(payload.get("results", []))
            after = (payload.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break
    finally:
        if client is None:
            await _client.aclose()

    return results


async def store_hubspot_connection(
    session: AsyncSession,
    workspace_id: UUID,
    token_response: dict,
) -> CrmConnection:
    """Encrypt and upsert the workspace's HubSpot OAuth connection."""
    from sqlalchemy import select, text

    from relay.config import get_settings
    from relay.crypto import encrypt_token, ensure_workspace_dek, kms_provider_from_settings
    from relay.db.models import CrmConnection as _CrmConnection, Workspace

    access_token = token_response["access_token"]
    refresh_token = token_response.get("refresh_token")
    scopes = token_response.get("scope", HUBSPOT_SCOPES)
    hubspot_portal_id = token_response.get("hub_id") or token_response.get("hubspot_portal_id")
    expires_in = token_response.get("expires_in")
    access_token_expires_at = None
    if expires_in is not None:
        access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    settings = get_settings()
    key = settings.token_encryption_key_bytes
    kms_provider = kms_provider_from_settings(settings)

    await session.execute(
        text("SELECT set_config('app.current_workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace_id)},
    )

    result = await session.execute(
        select(_CrmConnection).where(
            _CrmConnection.workspace_id == workspace_id,
            _CrmConnection.crm_provider == "hubspot",
        )
    )
    connection = result.scalar_one_or_none()

    if kms_provider is not None:
        workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = workspace_result.scalar_one()
        key = ensure_workspace_dek(workspace, key, kms_provider)

    encrypted_access_token, access_nonce = encrypt_token(access_token, key)
    encrypted_refresh_token = None
    refresh_nonce = None
    if refresh_token:
        encrypted_refresh_token, refresh_nonce = encrypt_token(refresh_token, key)

    if connection is None:
        connection = _CrmConnection(
            workspace_id=workspace_id,
            crm_provider="hubspot",
            encrypted_access_token=encrypted_access_token,
            encrypted_access_token_nonce=access_nonce,
            encrypted_refresh_token=encrypted_refresh_token,
            encrypted_refresh_token_nonce=refresh_nonce,
            scopes=scopes,
            hubspot_portal_id=str(hubspot_portal_id) if hubspot_portal_id is not None else None,
            access_token_expires_at=access_token_expires_at,
            sync_status="not_synced",
        )
        session.add(connection)
    else:
        connection.encrypted_access_token = encrypted_access_token
        connection.encrypted_access_token_nonce = access_nonce
        connection.encrypted_refresh_token = encrypted_refresh_token
        connection.encrypted_refresh_token_nonce = refresh_nonce
        connection.scopes = scopes
        connection.hubspot_portal_id = str(hubspot_portal_id) if hubspot_portal_id is not None else None
        connection.access_token_expires_at = access_token_expires_at
        connection.sync_status = "not_synced"
        connection.disconnected_at = None

    return connection
