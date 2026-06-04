import importlib


def test_health_endpoint(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")

    from fastapi.testclient import TestClient

    module = importlib.import_module("relay.api.main")
    client = TestClient(module.api)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "relay"}
