"""Smoke tests for the private beta setup flow (steps 1–6 of beta-validation-checklist.md).

These are unit tests that verify the SetupState progression through the four setup
steps: admin → channel → CRM → knowledge source. They use mocks and the DB integration
fixtures where a live DB is available, falling back to pure unit assertions otherwise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from relay.slack.home import SetupState, _connector_blocks, _setup_checklist_blocks, build_home


# ---------------------------------------------------------------------------
# Step 1 helpers
# ---------------------------------------------------------------------------

def _make_connector(connector_type: str, sync_status: str = "synced") -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.connector_type = connector_type
    row.sync_status = sync_status
    row.last_synced_at = datetime.now(UTC) - timedelta(hours=1)
    return row


# ---------------------------------------------------------------------------
# Step 1+2 — After install: admin bootstrapped, checklist 1/4
# ---------------------------------------------------------------------------

def test_post_install_setup_state_is_1_of_4():
    state = SetupState(admin_count=1, channel_count=0, crm_connected=False, source_count=0)
    texts = _setup_checklist_all_text(state)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_circle: Customer Slack Connect channel registered" in texts
    assert ":white_circle: HubSpot CRM connected" in texts
    assert ":white_circle: Knowledge source connected" in texts
    assert "Setup complete" not in texts


# ---------------------------------------------------------------------------
# Step 3 — After channel registration: checklist 2/4
# ---------------------------------------------------------------------------

def test_post_channel_registration_setup_state_is_2_of_4():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=False, source_count=0)
    texts = _setup_checklist_all_text(state)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_check_mark: Customer Slack Connect channel registered" in texts
    assert ":white_circle: HubSpot CRM connected" in texts
    assert ":white_circle: Knowledge source connected" in texts
    assert "Setup complete" not in texts


# ---------------------------------------------------------------------------
# Step 4 — After HubSpot OAuth: checklist 3/4
# ---------------------------------------------------------------------------

def test_post_hubspot_connect_setup_state_is_3_of_4():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=True, source_count=0)
    texts = _setup_checklist_all_text(state)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_check_mark: Customer Slack Connect channel registered" in texts
    assert ":white_check_mark: HubSpot CRM connected" in texts
    assert ":white_circle: Knowledge source connected" in texts
    assert "Setup complete" not in texts


# ---------------------------------------------------------------------------
# Step 5+6 — After knowledge source connected: checklist 4/4 → Setup complete
# ---------------------------------------------------------------------------

def test_post_knowledge_source_setup_state_is_4_of_4():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=True, source_count=1)
    texts = _setup_checklist_all_text(state)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_check_mark: Customer Slack Connect channel registered" in texts
    assert ":white_check_mark: HubSpot CRM connected" in texts
    assert ":white_check_mark: Knowledge source connected" in texts
    assert "Setup complete" in texts


def test_app_home_header_reads_setup_complete_when_all_done():
    state = SetupState(admin_count=1, channel_count=2, crm_connected=True, source_count=3)
    blocks = build_home([], setup_state=state)
    all_text = "\n".join(
        b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
    )
    assert ":tada: Setup complete" in all_text


# ---------------------------------------------------------------------------
# Connector block rendering in setup flow
# ---------------------------------------------------------------------------

def test_connected_github_source_appears_in_home():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=True, source_count=1)
    connector = _make_connector("github", "synced")
    blocks = build_home([connector], setup_state=state)
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    assert any("Github" in t or "github" in t.lower() for t in texts)


def test_connected_google_drive_source_appears_in_home():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=True, source_count=1)
    connector = _make_connector("google_drive", "synced")
    blocks = build_home([connector], setup_state=state)
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    assert any("Google Drive" in t for t in texts)


def test_failed_connector_exposes_retry_button_in_setup_flow():
    connector = _make_connector("github", "error")
    blocks = build_home([connector], setup_state=SetupState(admin_count=1))
    retry_actions = [
        el
        for b in blocks if b.get("type") == "actions"
        for el in b.get("elements", [])
        if el.get("action_id") == "relay_sync_connector"
    ]
    assert len(retry_actions) == 1


def test_multiple_connectors_each_have_disconnect_button():
    connectors = [
        _make_connector("github", "synced"),
        _make_connector("google_drive", "synced"),
    ]
    blocks = build_home(connectors)
    disconnect_buttons = [
        b.get("accessory")
        for b in blocks
        if b.get("accessory", {}).get("action_id") == "relay_disconnect_purge_connector"
    ]
    assert len(disconnect_buttons) == 2


# ---------------------------------------------------------------------------
# Zero-state: before any setup step
# ---------------------------------------------------------------------------

def test_zero_state_app_home_shows_no_checks():
    state = SetupState()
    texts = _setup_checklist_all_text(state)
    assert texts.count(":white_check_mark:") == 0
    assert texts.count(":white_circle:") == 4


def test_zero_state_app_home_shows_empty_connectors():
    blocks = build_home([], setup_state=SetupState())
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    assert any("No sources connected" in t for t in texts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_checklist_all_text(state: SetupState) -> str:
    blocks = _setup_checklist_blocks(state)
    return "\n".join(b.get("text", {}).get("text", "") for b in blocks)
