from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from relay.api.main import build_confirmation_token


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _client():
    module = importlib.import_module("relay.api.main")
    return module, TestClient(module.api)


def test_build_confirmation_token_signs_user_and_timestamp():
    workspace_id = uuid.uuid4()
    issued_at = 1_700_000_000
    token = build_confirmation_token(workspace_id, "U123", b"a" * 32, issued_at=issued_at)

    assert token.startswith(f"{issued_at}.")
    assert token == build_confirmation_token(workspace_id, "U123", b"a" * 32, issued_at=issued_at)
    assert token != build_confirmation_token(workspace_id, "U124", b"a" * 32, issued_at=issued_at)


def test_verify_confirmation_token_rejects_expired_token():
    module = importlib.import_module("relay.api.main")
    workspace_id = uuid.uuid4()
    issued_at = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    token = build_confirmation_token(workspace_id, "U123", b"a" * 32, issued_at=issued_at)

    with patch("relay.api.main.get_settings") as mock_settings:
        mock_settings.return_value.token_encryption_key_bytes = b"a" * 32
        assert module._verify_confirmation_token(workspace_id, "U123", token) is False


def test_erase_user_requires_valid_confirmation_token():
    module, client = _client()
    workspace_id = uuid.uuid4()
    unscoped = AsyncMock()
    unscoped.execute.return_value = _result(SimpleNamespace(id=workspace_id))

    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T123", "user_id": "UADMIN"})),
        patch("relay.api.main.get_session", return_value=_SessionContext(unscoped)),
        patch("relay.api.main.get_settings") as mock_settings,
    ):
        mock_settings.return_value.erasure_secret = "configured-secret"
        mock_settings.return_value.token_encryption_key_bytes = b"\xaa" * 32
        response = client.request(
            "DELETE",
            "/relay/admin/users/UERASE/erase",
            headers={"Authorization": "Bearer xoxb-test"},
            json={"confirmation_token": "bad"},
        )

    assert response.status_code == 403


def test_erase_user_nulls_pii_for_admin():
    module, client = _client()
    workspace_id = uuid.uuid4()
    admin = SimpleNamespace(id=uuid.uuid4(), slack_user_id="UADMIN", relay_role="admin")
    user = SimpleNamespace(
        id=uuid.uuid4(),
        slack_user_id="UERASE",
        relay_role="viewer",
        display_name="Erase Me",
        email="erase@example.com",
        deleted_at=None,
    )
    token = build_confirmation_token(workspace_id, "UERASE", b"\xaa" * 32)

    unscoped = AsyncMock()
    unscoped.execute.return_value = _result(SimpleNamespace(id=workspace_id))
    scoped = AsyncMock()
    scoped.add = MagicMock()
    scoped.execute = AsyncMock(
            side_effect=[
                _result(admin),
                _result(user),
                *[MagicMock() for _ in range(13)],
            ]
        )

    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T123", "user_id": "UADMIN"})),
        patch("relay.api.main.get_session", side_effect=[_SessionContext(unscoped), _SessionContext(scoped)]),
        patch("relay.api.main.get_settings") as mock_settings,
    ):
        mock_settings.return_value.token_encryption_key_bytes = b"\xaa" * 32
        response = client.request(
            "DELETE",
            "/relay/admin/users/UERASE/erase",
            headers={"Authorization": "Bearer xoxb-test"},
            json={"confirmation_token": token},
        )

    assert response.status_code == 200
    assert response.json() == {"erased": True, "user_id": str(user.id)}
    assert user.display_name is None
    assert user.email is None
    assert user.deleted_at is not None
    assert scoped.execute.call_count == 15
    assert scoped.add.call_args.args[0].event_type == "user_erased"
