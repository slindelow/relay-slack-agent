"""Unit tests for HubSpot OAuth helpers. All tests mock httpx — no network calls."""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from urllib.parse import parse_qs, urlparse

from relay.config import get_settings
from relay.crypto import decrypt_token
from relay.db.models import CrmConnection
from relay.integrations.hubspot import (
    HUBSPOT_AUTH_BASE,
    HubSpotAPIError,
    HubSpotOAuthError,
    build_hubspot_state,
    exchange_code_for_tokens,
    fetch_hubspot_companies,
    hubspot_oauth_url,
    parse_hubspot_state,
    refresh_access_token,
    store_hubspot_connection,
)
from relay.slack.oauth import upsert_workspace_from_install


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    async def post(self, url: str, data: dict, **kwargs) -> FakeResponse:
        self.posts.append({"url": url, "data": data})
        return self.response

    async def get(self, url: str, **kwargs) -> FakeResponse:
        self.gets.append({"url": url, "kwargs": kwargs})
        return self.response


# ---------------------------------------------------------------------------
# 1. URL builder
# ---------------------------------------------------------------------------


def test_hubspot_oauth_url_contains_required_params():
    url = hubspot_oauth_url(
        client_id="client-123",
        redirect_uri="https://relay.example.com/hubspot/oauth",
        state="workspace-state",
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert url.startswith(HUBSPOT_AUTH_BASE)
    assert params["client_id"] == ["client-123"]
    assert params["redirect_uri"] == ["https://relay.example.com/hubspot/oauth"]
    assert params["state"] == ["workspace-state"]
    scope_str = params["scope"][0]
    assert "crm.objects.companies.read" in scope_str
    assert "crm.objects.contacts.read" in scope_str
    assert "crm.objects.deals.read" in scope_str


def test_hubspot_oauth_state_round_trips_workspace_id():
    workspace_id = uuid.uuid4()
    state = build_hubspot_state(workspace_id, bytes.fromhex("a" * 64))

    assert parse_hubspot_state(state, bytes.fromhex("a" * 64)) == workspace_id


def test_hubspot_oauth_state_rejects_tampering():
    workspace_id = uuid.uuid4()
    state = build_hubspot_state(workspace_id, bytes.fromhex("a" * 64))
    payload, signature = state.split(".", 1)
    tampered_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")

    with pytest.raises(HubSpotOAuthError):
        parse_hubspot_state(f"{tampered_payload}.{signature}", bytes.fromhex("a" * 64))


def test_hubspot_oauth_state_rejects_malformed_input():
    with pytest.raises(HubSpotOAuthError):
        parse_hubspot_state("not-a-valid-state", bytes.fromhex("a" * 64))


def test_hubspot_oauth_state_rejects_expired_state():
    workspace_id = uuid.uuid4()
    signing_key = bytes.fromhex("a" * 64)
    issued_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    state = build_hubspot_state(workspace_id, signing_key, now=issued_at)

    with pytest.raises(HubSpotOAuthError):
        parse_hubspot_state(state, signing_key, max_age_seconds=600)


# ---------------------------------------------------------------------------
# 2. Token exchange — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_success():
    client = FakeAsyncClient(
        FakeResponse(200, {"access_token": "access", "refresh_token": "refresh", "expires_in": 1800})
    )
    tokens = await exchange_code_for_tokens(
        code="code-123",
        client_id="client",
        client_secret="secret",
        redirect_uri="https://relay.example.com/hubspot/oauth",
        client=client,
    )

    assert tokens["access_token"] == "access"
    assert tokens["refresh_token"] == "refresh"
    assert client.posts[0]["data"]["grant_type"] == "authorization_code"
    assert client.posts[0]["data"]["code"] == "code-123"


# ---------------------------------------------------------------------------
# 3. Token exchange — error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_raises_on_error():
    client = FakeAsyncClient(FakeResponse(400, text="bad code"))
    with pytest.raises(HubSpotOAuthError):
        await exchange_code_for_tokens(
            code="bad",
            client_id="client",
            client_secret="secret",
            redirect_uri="https://relay.example.com/hubspot/oauth",
            client=client,
        )


# ---------------------------------------------------------------------------
# 4. Token refresh — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_success():
    client = FakeAsyncClient(
        FakeResponse(200, {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 1800})
    )
    result = await refresh_access_token(
        refresh_token="old-refresh-token",
        client_id="client",
        client_secret="secret",
        client=client,
    )

    assert result["access_token"] == "new-access"
    assert result["refresh_token"] == "new-refresh"
    assert client.posts[0]["data"]["grant_type"] == "refresh_token"
    assert client.posts[0]["data"]["refresh_token"] == "old-refresh-token"


# ---------------------------------------------------------------------------
# 5. Fetch companies — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_companies_returns_results():
    companies = [
        {"id": "101", "properties": {"name": "Acme Corp", "domain": "acme.com"}},
        {"id": "102", "properties": {"name": "Beta Inc", "domain": "beta.io"}},
    ]
    client = FakeAsyncClient(FakeResponse(200, {"results": companies}))

    result = await fetch_hubspot_companies(access_token="valid-token", client=client)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "101"
    assert result[1]["properties"]["name"] == "Beta Inc"


# ---------------------------------------------------------------------------
# 6. Fetch companies — error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_companies_raises_on_error():
    client = FakeAsyncClient(FakeResponse(401, text="Unauthorized"))
    with pytest.raises(HubSpotAPIError):
        await fetch_hubspot_companies(access_token="expired-token", client=client)


@pytest.mark.asyncio
async def test_fetch_companies_follows_pagination():
    """Workspaces with >100 companies must sync fully via the paging cursor."""

    class PagingClient:
        def __init__(self, pages: list[FakeResponse]) -> None:
            self._pages = pages
            self.gets: list[dict] = []

        async def get(self, url: str, **kwargs) -> FakeResponse:
            self.gets.append({"url": url, "kwargs": kwargs})
            return self._pages[len(self.gets) - 1]

    page1 = FakeResponse(
        200,
        {
            "results": [{"id": "1", "properties": {"name": "A"}}],
            "paging": {"next": {"after": "100"}},
        },
    )
    page2 = FakeResponse(
        200,
        {"results": [{"id": "2", "properties": {"name": "B"}}]},  # no paging → last page
    )
    client = PagingClient([page1, page2])

    result = await fetch_hubspot_companies(access_token="valid-token", client=client)

    assert [c["id"] for c in result] == ["1", "2"]
    # Second request must carry the cursor from page 1.
    assert client.gets[1]["kwargs"]["params"]["after"] == "100"


# ---------------------------------------------------------------------------
# Integration: store_hubspot_connection (skipped automatically when no DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_hubspot_connection_encrypts_and_upserts(db_session, relay_settings):
    workspace = await upsert_workspace_from_install(
        db_session,
        slack_team_id="T_HUBSPOT_001",
        slack_team_name="HubSpot Corp",
    )
    await db_session.flush()

    connection = await store_hubspot_connection(
        db_session,
        workspace.id,
        {
            "access_token": "access-token-1",
            "refresh_token": "refresh-token-1",
            "scope": "crm.objects.companies.read",
            "hub_id": 12345,
            "expires_in": 1800,
        },
    )
    await db_session.flush()

    assert connection.crm_provider == "hubspot"
    assert connection.encrypted_access_token != b"access-token-1"
    assert connection.encrypted_refresh_token != b"refresh-token-1"
    assert connection.hubspot_portal_id == "12345"
    assert connection.access_token_expires_at is not None
    assert connection.disconnected_at is None

    key = get_settings().token_encryption_key_bytes
    assert decrypt_token(connection.encrypted_access_token, connection.encrypted_access_token_nonce, key) == "access-token-1"
    assert decrypt_token(connection.encrypted_refresh_token, connection.encrypted_refresh_token_nonce, key) == "refresh-token-1"

    updated = await store_hubspot_connection(
        db_session,
        workspace.id,
        {"access_token": "access-token-2", "refresh_token": "refresh-token-2"},
    )
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(CrmConnection).where(
                CrmConnection.workspace_id == workspace.id,
                CrmConnection.crm_provider == "hubspot",
            )
        )
    ).scalars().all()

    assert updated.id == connection.id
    assert len(rows) == 1
    assert decrypt_token(updated.encrypted_access_token, updated.encrypted_access_token_nonce, key) == "access-token-2"
