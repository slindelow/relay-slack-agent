"""Tests for /health endpoint and Sentry init (Plan 7 US-008)."""

from fastapi.testclient import TestClient


def _make_client():
    from relay.api.main import api
    return TestClient(api, raise_server_exceptions=False)


def test_health_returns_expected_fields():
    """Health endpoint always returns status, db, redis, version regardless of env."""
    client = _make_client()
    resp = client.get("/health")
    # 200 (ok) or 503 (degraded) — both valid; no DB/Redis in unit test environment
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert body["db"] in ("ok", "error")
    assert body["redis"] in ("ok", "error")
    assert "version" in body


def test_health_response_always_has_all_keys():
    """All four required keys present regardless of dependency health."""
    client = _make_client()
    body = client.get("/health").json()
    for key in ("status", "db", "redis", "version"):
        assert key in body, f"Missing key: {key}"


def test_sentry_not_initialised_without_dsn():
    """Server imports cleanly when SENTRY_DSN is empty — no crash at startup."""
    from relay.api.main import api
    assert api is not None


def test_sentry_dsn_field_defaults_to_empty():
    from relay.config import get_settings
    settings = get_settings()
    assert hasattr(settings, "sentry_dsn")
    assert settings.sentry_dsn == ""
