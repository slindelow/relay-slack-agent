def test_process_event_is_celery_task(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    from relay.worker.tasks import process_slack_event

    assert hasattr(process_slack_event, "delay")


def test_dedup_key_is_deterministic(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    from relay.worker.tasks import make_dedup_key

    assert make_dedup_key("T1", "C1", "123.456") == make_dedup_key("T1", "C1", "123.456")
    assert make_dedup_key("T1", "C1", "123.456") != make_dedup_key("T1", "C1", "123.457")


async def _setup_settings(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example/0")
    from relay.config import get_settings

    get_settings.cache_clear()


def test_claim_event_dedup_key_uses_redis_set_nx(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch

    asyncio.run(_setup_settings(monkeypatch))

    class FakeRedis:
        def __init__(self):
            self.set = AsyncMock(return_value=True)
            self.aclose = AsyncMock()

    fake = FakeRedis()

    with patch("redis.asyncio.from_url", return_value=fake) as from_url:
        from relay.worker.tasks import claim_event_dedup_key

        claimed = asyncio.run(claim_event_dedup_key("event:T:C:1", ttl_seconds=60))

    assert claimed is True
    from_url.assert_called_once()
    fake.set.assert_awaited_once_with("event:T:C:1", "1", ex=60, nx=True)
    fake.aclose.assert_awaited_once()


def test_claim_event_dedup_key_duplicate_returns_false(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, patch

    asyncio.run(_setup_settings(monkeypatch))

    class FakeRedis:
        def __init__(self):
            self.set = AsyncMock(return_value=None)
            self.aclose = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=FakeRedis()):
        from relay.worker.tasks import claim_event_dedup_key

        assert asyncio.run(claim_event_dedup_key("event:T:C:1", ttl_seconds=60)) is False


def test_claim_event_dedup_key_fails_open_on_redis_error(monkeypatch):
    import asyncio
    from unittest.mock import patch

    asyncio.run(_setup_settings(monkeypatch))

    with patch("redis.asyncio.from_url", side_effect=RuntimeError("redis down")):
        from relay.worker.tasks import claim_event_dedup_key

        assert asyncio.run(claim_event_dedup_key("event:T:C:1", ttl_seconds=60)) is True
