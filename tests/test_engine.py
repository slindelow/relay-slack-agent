"""Engine pool selection: worker uses NullPool to survive per-task event loops."""

import importlib

from sqlalchemy.pool import NullPool


def _fresh_engine_module(monkeypatch, service_type: str | None):
    if service_type is None:
        monkeypatch.delenv("SERVICE_TYPE", raising=False)
    else:
        monkeypatch.setenv("SERVICE_TYPE", service_type)
    import relay.db.engine as engine_module

    importlib.reload(engine_module)
    return engine_module


def test_worker_engine_uses_nullpool(monkeypatch):
    engine_module = _fresh_engine_module(monkeypatch, "worker")
    try:
        engine = engine_module.get_engine()
        assert isinstance(engine.pool, NullPool)
    finally:
        # Restore default module state for other tests.
        monkeypatch.delenv("SERVICE_TYPE", raising=False)
        importlib.reload(engine_module)


def test_web_engine_keeps_pool(monkeypatch):
    engine_module = _fresh_engine_module(monkeypatch, "web")
    try:
        engine = engine_module.get_engine()
        assert not isinstance(engine.pool, NullPool)
    finally:
        monkeypatch.delenv("SERVICE_TYPE", raising=False)
        importlib.reload(engine_module)
