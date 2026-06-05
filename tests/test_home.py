"""Unit tests for App Home build_home()."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from relay.slack.home import build_home


def _make_connector(connector_type: str, sync_status: str, last_synced_at: datetime | None = None) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.connector_type = connector_type
    row.sync_status = sync_status
    row.last_synced_at = last_synced_at
    row.disconnected_at = None
    return row


def test_build_home_no_connectors():
    blocks = build_home([])
    texts = [b.get("text", {}).get("text", "") for b in blocks]
    assert any("No sources connected" in t for t in texts)


def test_build_home_with_google_drive_connector():
    connector = _make_connector("google_drive", "synced", datetime.now(UTC) - timedelta(hours=2))
    blocks = build_home([connector])

    # Find the connector block
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    connector_text = next((t for t in texts if "Google Drive" in t), None)
    assert connector_text is not None
    assert ":page_facing_up:" in connector_text
    assert "synced" in connector_text.lower()


def test_build_home_connector_shows_sync_status():
    connector = _make_connector("github", "error", datetime.now(UTC) - timedelta(hours=1))
    blocks = build_home([connector])

    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    connector_text = next((t for t in texts if "Github" in t or "github" in t.lower()), None)
    assert connector_text is not None
    assert "error" in connector_text.lower()


def test_build_home_staleness_warning():
    old_time = datetime.now(UTC) - timedelta(hours=30)
    connector = _make_connector("google_drive", "synced", old_time)
    blocks = build_home([connector])

    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    connector_text = next((t for t in texts if "Google Drive" in t), None)
    assert connector_text is not None
    assert "stale" in connector_text.lower() or "24h" in connector_text


def test_build_home_no_staleness_when_fresh():
    fresh_time = datetime.now(UTC) - timedelta(hours=1)
    connector = _make_connector("github", "synced", fresh_time)
    blocks = build_home([connector])

    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    connector_text = next((t for t in texts if "Github" in t or "github" in t.lower()), None)
    assert connector_text is not None
    assert "stale" not in connector_text.lower()


def test_connected_sources_header_present():
    blocks = build_home([])
    headers = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "header"]
    assert any("Connected Sources" in h for h in headers)
