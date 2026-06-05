"""HubSpot OAuth flow and account sync."""

from __future__ import annotations

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
            f"Token exchange failed: {response.status_code} {response.text}"
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
            f"Token refresh failed: {response.status_code} {response.text}"
        )
    return response.json()


async def fetch_hubspot_companies(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch company objects from HubSpot CRM API."""
    params = {
        "limit": limit,
        "properties": "name,domain,hs_lead_status,dealtype,createdate,hs_analytics_source",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    _client = client or httpx.AsyncClient()
    try:
        response = await _client.get(
            HUBSPOT_COMPANIES_URL,
            params=params,
            headers=headers,
        )
    finally:
        if client is None:
            await _client.aclose()

    if response.status_code != 200:
        raise HubSpotAPIError(
            f"Companies fetch failed: {response.status_code} {response.text}"
        )
    return response.json().get("results", [])


async def store_hubspot_connection(
    session: AsyncSession,
    workspace_id: UUID,
    token_response: dict,
) -> CrmConnection:
    """Encrypt and upsert the workspace's HubSpot OAuth connection."""
    from sqlalchemy import select, text

    from relay.config import get_settings
    from relay.crypto import encrypt_token
    from relay.db.models import CrmConnection as _CrmConnection

    access_token = token_response["access_token"]
    refresh_token = token_response.get("refresh_token")
    scopes = token_response.get("scope", HUBSPOT_SCOPES)
    key = get_settings().token_encryption_key_bytes

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
            sync_status="not_synced",
        )
        session.add(connection)
    else:
        connection.encrypted_access_token = encrypted_access_token
        connection.encrypted_access_token_nonce = access_nonce
        connection.encrypted_refresh_token = encrypted_refresh_token
        connection.encrypted_refresh_token_nonce = refresh_nonce
        connection.scopes = scopes
        connection.sync_status = "not_synced"
        connection.disconnected_at = None

    return connection
