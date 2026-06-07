import importlib
from unittest.mock import AsyncMock, patch


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
    assert response.json() == {"status": "ok", "service": "relay", "db": "ok", "redis": "ok"}


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
