"""Tests for GDPR user erasure endpoint (Plan 7 US-004)."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_client():
    from relay.api.main import api
    return TestClient(api, raise_server_exceptions=False)


def _token(slack_user_id: str, secret: str = "") -> str:
    return hashlib.sha256((slack_user_id + secret).encode()).hexdigest()


def test_erase_missing_bearer_returns_401():
    client = _make_client()
    resp = client.request(
        "DELETE",
        "/relay/admin/users/U123/erase",
        params={"confirmation_token": "anything"},
    )
    assert resp.status_code == 401


def test_erase_wrong_confirmation_token_returns_400():
    client = _make_client()
    with patch("relay.api.main._slack_auth_test", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = {"team_id": "T1", "user_id": "Uadmin"}
        resp = client.request(
            "DELETE",
            "/relay/admin/users/U123/erase",
            headers={"Authorization": "Bearer xoxb-test"},
            params={"confirmation_token": "wrong-token"},
        )
    assert resp.status_code == 400


def test_erase_non_admin_returns_403():
    client = _make_client()

    mock_workspace = MagicMock()
    mock_workspace.id = __import__("uuid").uuid4()

    mock_admin_user = MagicMock()
    mock_admin_user.relay_role = "viewer"  # not admin

    unscoped_ctx = AsyncMock()
    unscoped_ctx.__aenter__ = AsyncMock(return_value=unscoped_ctx)
    unscoped_ctx.__aexit__ = AsyncMock(return_value=False)
    unscoped_ctx.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_workspace))
    )

    scoped_ctx = AsyncMock()
    scoped_ctx.__aenter__ = AsyncMock(return_value=scoped_ctx)
    scoped_ctx.__aexit__ = AsyncMock(return_value=False)
    scoped_ctx.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_admin_user))
    )

    def session_factory(workspace_id=None):
        return unscoped_ctx if workspace_id is None else scoped_ctx

    target_user = "U123"
    tok = _token(target_user)

    with (
        patch("relay.api.main._slack_auth_test", new_callable=AsyncMock) as mock_auth,
        patch("relay.api.main.get_session", side_effect=session_factory),
    ):
        mock_auth.return_value = {"team_id": "T1", "user_id": "Uadmin"}
        resp = client.request(
            "DELETE",
            f"/relay/admin/users/{target_user}/erase",
            headers={"Authorization": "Bearer xoxb-test"},
            params={"confirmation_token": tok},
        )
    assert resp.status_code == 403
