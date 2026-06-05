"""Unit tests for relay/sla/alerts.py — no external deps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from relay.sla.alerts import build_alert_blocks, _human_duration


# ---------------------------------------------------------------------------
# _human_duration
# ---------------------------------------------------------------------------


def test_duration_seconds():
    assert _human_duration(45) == "45s"


def test_duration_minutes():
    assert _human_duration(90) == "1m"
    assert _human_duration(150) == "2m"


def test_duration_hours_exact():
    assert _human_duration(3600) == "1h"
    assert _human_duration(7200) == "2h"


def test_duration_hours_and_minutes():
    assert _human_duration(3660) == "1h 1m"   # 3600 + 60
    assert _human_duration(3690) == "1h 1m"   # 3600 + 90
    assert _human_duration(5400) == "1h 30m"  # 3600 + 1800


# ---------------------------------------------------------------------------
# build_alert_blocks structure
# ---------------------------------------------------------------------------


def _make_blocks(**kwargs) -> list[dict]:
    defaults = dict(
        question_id=uuid.uuid4(),
        title_excerpt="How do I configure SSO?",
        account_name="Acme Corp",
        account_tier="enterprise",
        created_at=datetime.now(UTC) - timedelta(hours=2),
        sla_deadline=datetime.now(UTC) + timedelta(hours=4),
        alert_count=0,
    )
    defaults.update(kwargs)
    return build_alert_blocks(**defaults)


def test_build_alert_blocks_returns_list():
    blocks = _make_blocks()
    assert isinstance(blocks, list)
    assert len(blocks) >= 3


def test_build_alert_blocks_has_actions():
    blocks = _make_blocks()
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    assert len(action_blocks) == 1
    elements = action_blocks[0]["elements"]
    assert len(elements) == 4


def test_build_alert_blocks_claim_is_primary_action():
    blocks = _make_blocks()
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    elements = action_blocks[0]["elements"]
    claim = next(e for e in elements if e["action_id"] == "relay_claim_question")
    assert claim["style"] == "primary"


def test_build_alert_blocks_has_snooze_actions():
    blocks = _make_blocks()
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    elements = action_blocks[0]["elements"]
    action_ids = {e["action_id"] for e in elements}
    assert "relay_snooze_1h" in action_ids
    assert "relay_snooze_4h" in action_ids


def test_build_alert_blocks_has_not_a_question_action():
    blocks = _make_blocks()
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    elements = action_blocks[0]["elements"]
    not_q = next(e for e in elements if e["action_id"] == "relay_mark_not_question")
    assert not_q["style"] == "danger"


def test_build_alert_blocks_escalation_note_on_second_alert():
    blocks = _make_blocks(alert_count=1)
    section = blocks[0]
    assert "Escalation" in section["text"]["text"]


def test_build_alert_blocks_no_escalation_on_first_alert():
    blocks = _make_blocks(alert_count=0)
    section = blocks[0]
    assert "Escalation" not in section["text"]["text"]


def test_build_alert_blocks_sla_breached_shows_red():
    past_deadline = datetime.now(UTC) - timedelta(hours=1)
    blocks = _make_blocks(sla_deadline=past_deadline)
    fields_text = str(blocks)
    assert "breached" in fields_text.lower()


def test_build_alert_blocks_no_sla_policy():
    blocks = _make_blocks(sla_deadline=None)
    fields_text = str(blocks)
    assert "No SLA policy" in fields_text


def test_build_alert_blocks_question_id_in_action_values():
    q_id = uuid.uuid4()
    blocks = _make_blocks(question_id=q_id)
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    elements = action_blocks[0]["elements"]
    for element in elements:
        assert element["value"] == str(q_id)


def test_build_alert_blocks_truncates_long_title():
    long_title = "x" * 500
    blocks = _make_blocks(title_excerpt=long_title)
    # Should not propagate >200 chars into the block
    fields_text = str(blocks)
    # The "x" * 201 should not appear
    assert "x" * 201 not in fields_text
