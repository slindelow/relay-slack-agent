"""Unit tests for App Home build_home()."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from relay.slack.home import SetupState, build_home


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
    assert any("main message box" in t for t in texts)
    assert any("thread replies" in t for t in texts)


def test_build_home_setup_state_reflects_progress():
    blocks = build_home(
        [],
        setup_state=SetupState(
            admin_count=1,
            channel_count=1,
            crm_connected=True,
            source_count=0,
        ),
    )
    text = "\n".join(block.get("text", {}).get("text", "") for block in blocks)
    assert "RELAY admin configured" in text
    assert "HubSpot CRM connected" in text
    assert ":white_circle: Knowledge source connected" in text


def test_build_home_with_google_drive_connector():
    connector = _make_connector("google_drive", "synced", datetime.now(UTC) - timedelta(hours=2))
    blocks = build_home([connector])

    # Find the connector block
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    connector_text = next((t for t in texts if "Google Drive" in t), None)
    assert connector_text is not None
    assert ":page_facing_up:" in connector_text
    assert "synced" in connector_text.lower()
    accessories = [b.get("accessory", {}) for b in blocks if b.get("accessory")]
    assert any(button.get("action_id") == "relay_disconnect_purge_connector" for button in accessories)


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


def test_build_home_drafts_ready_section_renders_review_button():
    draft_id = str(uuid.uuid4())
    blocks = build_home(
        [],
        pending_drafts=[{"draft_id": draft_id, "excerpt": "When does our contract renew?"}],
    )
    headers = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "header"]
    assert any("Drafts Ready for Review" in h for h in headers)
    review_buttons = [
        b["accessory"]
        for b in blocks
        if b.get("accessory", {}).get("action_id") == "relay_open_draft_modal"
    ]
    assert len(review_buttons) == 1
    assert review_buttons[0]["value"] == draft_id


def test_build_home_no_drafts_ready_section_when_empty():
    blocks = build_home([], pending_drafts=[])
    headers = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "header"]
    assert not any("Drafts Ready for Review" in h for h in headers)


def _make_impact(sla_met, draft_accepted, time_to_send_seconds):
    row = MagicMock()
    row.sla_met = sla_met
    row.draft_accepted = draft_accepted
    row.time_to_send_seconds = time_to_send_seconds
    return row


def test_build_home_impact_no_data_message():
    blocks = build_home([], impact_rows=[])
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    assert any("No data yet" in text for text in texts)


def test_build_home_impact_metrics_section():
    impact_rows = [
        _make_impact(True, True, 272),
        _make_impact(True, False, 60),
        _make_impact(False, True, 120),
    ]

    blocks = build_home([], impact_rows=impact_rows)

    fields = [
        field["text"]
        for block in blocks
        for field in block.get("fields", [])
    ]
    joined = "\n".join(fields)
    assert "66.7%" in joined
    assert "Draft accepted rate" in joined
    assert "2m 0s" in joined
    assert "Questions handled" in joined


def _make_feedback(correction_action: str):
    row = MagicMock()
    row.correction_action = correction_action
    return row


def test_build_home_accuracy_no_corrections_message():
    blocks = build_home([], feedback_rows=[], total_questions_7d=12, feedback_export_url="https://relay.example.com/export")
    texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
    buttons = [b.get("accessory", {}) for b in blocks if b.get("accessory")]

    assert any("No corrections this week" in text for text in texts)
    assert any(button.get("url") == "https://relay.example.com/export" for button in buttons)


def test_build_home_accuracy_metrics_section():
    feedback_rows = [
        _make_feedback("mark_not_question"),
        _make_feedback("mark_not_question"),
        _make_feedback("regenerate_draft"),
    ]

    blocks = build_home([], feedback_rows=feedback_rows, total_questions_7d=20)

    fields = [
        field["text"]
        for block in blocks
        for field in block.get("fields", [])
    ]
    joined = "\n".join(fields)
    assert "Corrections this week" in joined
    assert "2" in joined
    assert "90.0%" in joined


# ---------------------------------------------------------------------------
# Dynamic setup checklist
# ---------------------------------------------------------------------------

def _all_texts(blocks: list) -> str:
    parts = []
    for b in blocks:
        t = b.get("text", {})
        if isinstance(t, dict):
            parts.append(t.get("text", ""))
        for f in b.get("fields", []):
            parts.append(f.get("text", ""))
    return "\n".join(parts)


def test_setup_checklist_all_incomplete():
    blocks = build_home([], setup_state=SetupState())
    texts = _all_texts(blocks)
    assert ":white_circle: RELAY admin configured" in texts
    assert ":white_circle: Customer Slack Connect channel registered" in texts
    assert ":white_circle: HubSpot CRM connected" in texts
    assert ":white_circle: Knowledge source connected" in texts


def test_setup_checklist_partial_completion():
    state = SetupState(admin_count=1, channel_count=1, crm_connected=False, source_count=0)
    blocks = build_home([], setup_state=state)
    texts = _all_texts(blocks)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_check_mark: Customer Slack Connect channel registered" in texts
    assert ":white_circle: HubSpot CRM connected" in texts
    assert ":white_circle: Knowledge source connected" in texts


def test_setup_checklist_all_complete():
    state = SetupState(admin_count=2, channel_count=3, crm_connected=True, source_count=1)
    blocks = build_home([], setup_state=state)
    texts = _all_texts(blocks)
    assert ":white_check_mark: RELAY admin configured" in texts
    assert ":white_check_mark: Customer Slack Connect channel registered" in texts
    assert ":white_check_mark: HubSpot CRM connected" in texts
    assert ":white_check_mark: Knowledge source connected" in texts
    assert "Setup complete" in texts


def test_error_connector_shows_retry_sync_button():
    connector = _make_connector("github", "error", datetime.now(UTC) - timedelta(hours=1))
    blocks = build_home([connector])
    action_blocks = [b for b in blocks if b.get("type") == "actions"]
    retry_elements = [
        el
        for b in action_blocks
        for el in b.get("elements", [])
        if el.get("action_id") == "relay_sync_connector"
    ]
    assert len(retry_elements) == 1
    assert retry_elements[0]["text"]["text"] == "Retry sync"
    assert retry_elements[0]["value"] == str(connector.id)


def test_synced_connector_has_no_retry_button():
    connector = _make_connector("github", "synced", datetime.now(UTC) - timedelta(hours=1))
    blocks = build_home([connector])
    action_blocks = [b for b in blocks if b.get("type") == "actions"]
    retry_elements = [
        el
        for b in action_blocks
        for el in b.get("elements", [])
        if el.get("action_id") == "relay_sync_connector"
    ]
    assert len(retry_elements) == 0
