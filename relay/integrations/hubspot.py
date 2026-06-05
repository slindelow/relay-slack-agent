"""HubSpot OAuth flow and account sync."""

from urllib.parse import urlencode

import httpx

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
