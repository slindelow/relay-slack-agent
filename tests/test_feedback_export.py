from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


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


def _scalars_result(values):
    result = MagicMock()
    result.scalars.return_value = values
    return result


def _client():
    module = importlib.import_module("relay.api.main")
    return module, TestClient(module.api)


def test_feedback_export_requires_admin(monkeypatch):
    module, client = _client()
    workspace_id = uuid.uuid4()
    unscoped = AsyncMock()
    unscoped.execute.return_value = _result(SimpleNamespace(id=workspace_id))
    scoped = AsyncMock()
    scoped.execute.return_value = _result(SimpleNamespace(relay_role="viewer"))

    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T123", "user_id": "U123"})),
        patch("relay.api.main.get_session", side_effect=[_SessionContext(unscoped), _SessionContext(scoped)]),
    ):
        response = client.get(
            "/relay/admin/feedback-export",
            headers={"Authorization": "Bearer xoxb-test"},
        )

    assert response.status_code == 403


def test_feedback_export_returns_jsonl_for_admin(monkeypatch):
    module, client = _client()
    workspace_id = uuid.uuid4()
    row_id = uuid.uuid4()
    question_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    message_id = uuid.uuid4()
    created_at = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)

    unscoped = AsyncMock()
    unscoped.execute.return_value = _result(SimpleNamespace(id=workspace_id))

    scoped = AsyncMock()
    admin_result = _result(SimpleNamespace(relay_role="admin"))
    feedback_row = SimpleNamespace(
        id=row_id,
        workspace_id=workspace_id,
        actor_user_id="U123",
        question_id=question_id,
        draft_id=draft_id,
        message_id=message_id,
        correction_action="mark_not_question",
        original_label=True,
        corrected_label=False,
        original_confidence=0.91,
        notes="False positive",
        created_at=created_at,
    )
    feedback_result = _scalars_result([feedback_row])
    scoped.execute = AsyncMock(side_effect=[admin_result, feedback_result])

    with (
        patch("relay.api.main._slack_auth_test", new=AsyncMock(return_value={"team_id": "T123", "user_id": "U123"})),
        patch("relay.api.main.get_session", side_effect=[_SessionContext(unscoped), _SessionContext(scoped)]),
    ):
        response = client.get(
            "/relay/admin/feedback-export?days=7",
            headers={"Authorization": "Bearer xoxb-test"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert "relay-feedback-" in response.headers["content-disposition"]
    body = response.text.strip()
    assert '"correction_action":"mark_not_question"' in body
    assert f'"workspace_id":"{workspace_id}"' in body
    assert f'"question_id":"{question_id}"' in body
    assert f'"id":"{row_id}"' in body
    assert '"actor_user_id":"U123"' in body


def test_feedback_export_days_over_90_is_rejected():
    _module, client = _client()
    response = client.get(
        "/relay/admin/feedback-export?days=120",
        headers={"Authorization": "Bearer xoxb-test"},
    )
    assert response.status_code == 422


def test_feedback_export_missing_auth_header():
    _module, client = _client()
    response = client.get("/relay/admin/feedback-export")
    assert response.status_code == 401


def test_feedback_export_slack_api_failure():
    from fastapi import HTTPException as FastAPIHTTPException

    _module, client = _client()
    with patch(
        "relay.api.main._slack_auth_test",
        new=AsyncMock(side_effect=FastAPIHTTPException(status_code=503, detail="Slack API unavailable")),
    ):
        response = client.get(
            "/relay/admin/feedback-export",
            headers={"Authorization": "Bearer xoxb-test"},
        )
    assert response.status_code == 503
