import importlib
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse


def _client(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")

    from fastapi.testclient import TestClient

    module = importlib.import_module("relay.api.main")
    return module, TestClient(module.api)


def test_health_endpoint(monkeypatch):
    module, client = _client(monkeypatch)

    with (
        patch("relay.api.main._check_db", new=AsyncMock(return_value="ok")),
        patch("relay.api.main._check_redis", new=AsyncMock(return_value="ok")),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "relay"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert "git_sha" in body
    assert "mcp_mounted" in body


def test_health_endpoint_returns_503_when_dependency_fails(monkeypatch):
    module, client = _client(monkeypatch)

    with (
        patch("relay.api.main._check_db", new=AsyncMock(return_value="ok")),
        patch("relay.api.main._check_redis", new=AsyncMock(return_value="error")),
    ):
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["redis"] == "error"


def test_legal_pages_are_public(monkeypatch):
    module, client = _client(monkeypatch)

    for path in ("/privacy", "/terms", "/sub-processors"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_beta_install_page_links_to_slack_install(monkeypatch):
    module, client = _client(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert "Add to Slack" in response.text
    assert "https://relay.example.com/slack/install" in response.text


def test_slack_search_install_uses_main_slack_redirect(monkeypatch):
    module, client = _client(monkeypatch)

    response = client.get(
        "/slack/search/install?team_id=T123&user_id=U123",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)
    assert params["redirect_uri"] == ["https://relay.example.com/slack/oauth_redirect"]
    assert params["client_id"] == ["client"]
    assert params["user_scope"] == ["search:read.public,search:read.files,search:read.users"]


def test_main_slack_redirect_dispatches_search_oauth_state(monkeypatch):
    module, client = _client(monkeypatch)
    state = module.build_slack_search_state(
        "T123",
        "U123",
        module.get_settings().token_encryption_key_bytes,
    )
    calls = []

    async def fake_search_callback(**kwargs):
        from fastapi.responses import JSONResponse

        calls.append(kwargs)
        return JSONResponse({"ok": True, "redirect_uri": kwargs["redirect_uri"]})

    with (
        patch("relay.api.main._handle_slack_search_oauth_callback", new=fake_search_callback),
        patch("relay.api.main.handler.handle", new=AsyncMock()) as mock_bolt,
    ):
        response = client.get(f"/slack/oauth_redirect?code=abc&state={state}")

    assert response.status_code == 200
    assert response.json()["redirect_uri"] == "https://relay.example.com/slack/oauth_redirect"
    assert len(calls) == 1
    mock_bolt.assert_not_awaited()


def test_legal_pages_use_configurable_contact_emails(monkeypatch):
    monkeypatch.setenv("PRIVACY_CONTACT_EMAIL", "privacy@acme.io")
    monkeypatch.setenv("LEGAL_CONTACT_EMAIL", "legal@acme.io")

    from relay.config import get_settings
    get_settings.cache_clear()

    module, client = _client(monkeypatch)

    try:
        privacy = client.get("/privacy")
        assert "privacy@acme.io" in privacy.text

        terms = client.get("/terms")
        assert "legal@acme.io" in terms.text
    finally:
        get_settings.cache_clear()
