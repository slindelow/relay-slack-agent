from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

from relay.slack.draft_modal import _confidence_badge, _renewal_proximity, build_draft_modal


def _draft(confidence=0.9, sources=None, customer_draft="Enable SSO under Settings > Security."):
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        evidence_bundle={"sources": sources or []},
        internal_brief="Use the SSO docs.",
        confidence=confidence,
        customer_draft=customer_draft,
    )


def _question(title="How do I configure SSO?"):
    return SimpleNamespace(title_excerpt=title)


def test_build_draft_modal_uses_question_title_excerpt():
    draft = _draft()
    question = _question()

    modal = build_draft_modal(draft, question, None)
    text_blocks = [
        block["text"]["text"]
        for block in modal["blocks"]
        if block.get("type") == "section" and "text" in block
    ]

    assert any("How do I configure SSO?" in text for text in text_blocks)


def test_confidence_badge_high():
    assert "high" in _confidence_badge(0.9)
    assert "high" in _confidence_badge(0.8)


def test_confidence_badge_medium():
    assert "medium" in _confidence_badge(0.7)
    assert "medium" in _confidence_badge(0.5)


def test_confidence_badge_low():
    assert "low" in _confidence_badge(0.4)


def test_confidence_badge_unknown():
    assert "unknown" in _confidence_badge(None)


def test_renewal_proximity_overdue():
    assert "OVERDUE" in _renewal_proximity("2020-01-01")


def test_renewal_proximity_soon():
    soon = (date.today() + timedelta(days=10)).isoformat()
    result = _renewal_proximity(soon)
    assert "warning" in result or "10" in result


def test_renewal_proximity_none():
    assert _renewal_proximity(None) == "N/A"


def test_modal_has_send_button():
    modal = build_draft_modal(_draft(), _question(), None)
    assert modal["submit"]["text"] == "Send"


def test_modal_has_action_buttons():
    modal = build_draft_modal(_draft(), _question(), None)
    all_text = json.dumps(modal)
    assert "relay_regenerate_draft" in all_text
    assert "relay_discard_draft" in all_text


def test_modal_private_metadata_contains_ids():
    draft = _draft()
    modal = build_draft_modal(draft, _question(), None)
    meta = json.loads(modal["private_metadata"])
    assert meta["draft_id"] == str(draft.id)
    assert "workspace_id" in meta


def test_modal_source_citations_rendered():
    sources = [
        {"title": "Issue #42", "provider": "github", "url": "https://github.com/org/repo/issues/42",
         "excerpt": "Rate limit details", "stale": False}
    ]
    modal = build_draft_modal(_draft(sources=sources), _question(), None)
    all_text = json.dumps(modal)
    assert "Issue #42" in all_text
    assert "github" in all_text


def test_build_home_with_questions_needing_draft():
    """build_home() with questions_needing_draft shows Generate draft buttons."""
    from relay.slack.home import build_home

    q = SimpleNamespace(id=uuid.uuid4(), body="Customer asked about outage")
    blocks = build_home(connector_rows=[], questions_needing_draft=[q])

    all_text = json.dumps(blocks)
    assert "relay_generate_draft" in all_text
    assert str(q.id) in all_text
