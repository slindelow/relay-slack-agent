import pytest

from relay.config import Settings


def base_env(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")


def test_settings_load_from_env(monkeypatch):
    base_env(monkeypatch)
    settings = Settings()
    assert settings.slack_client_id == "client"
    assert len(settings.token_encryption_key_bytes) == 32


def test_invalid_key_length_raises(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "tooshort")
    with pytest.raises(Exception):
        Settings()


def test_non_hex_key_raises(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "z" * 64)
    with pytest.raises(Exception):
        Settings()


def test_invalid_threshold_order_raises(monkeypatch):
    base_env(monkeypatch)
    monkeypatch.setenv("CLASSIFIER_OPEN_THRESHOLD", "0.5")
    monkeypatch.setenv("CLASSIFIER_CANDIDATE_THRESHOLD", "0.8")
    with pytest.raises(Exception):
        Settings()

