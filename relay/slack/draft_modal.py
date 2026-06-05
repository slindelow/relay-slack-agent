"""Block Kit modal builder for draft review (US-005). Pure function — no DB or Slack calls."""

from __future__ import annotations

import json
from typing import Any


def _confidence_badge(confidence: float | None) -> str:
    if confidence is None:
        return ":white_circle: unknown"
    if confidence >= 0.8:
        return ":large_green_circle: high confidence"
    if confidence >= 0.5:
        return ":large_yellow_circle: medium confidence"
    return ":red_circle: low confidence"


def _renewal_proximity(renewal_date_iso: str | None) -> str:
    if not renewal_date_iso:
        return "N/A"
    try:
        from datetime import date
        renewal = date.fromisoformat(renewal_date_iso)
        days = (renewal - date.today()).days
        if days < 0:
            return f"OVERDUE ({abs(days)}d ago)"
        if days <= 30:
            return f":warning: {days}d away"
        return f"{days}d away"
    except Exception:
        return renewal_date_iso


def build_draft_modal(
    draft_row: Any,
    question_row: Any,
    account_row: Any | None,
) -> dict:
    """Return Block Kit view payload for draft review. Pure — no side effects."""
    private_metadata = json.dumps({
        "draft_id": str(draft_row.id),
        "workspace_id": str(draft_row.workspace_id),
    })

    blocks: list[dict] = []

    # Question excerpt
    question_text = (getattr(question_row, "title_excerpt", "") or "")[:500] if question_row else ""
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Customer question:*\n{question_text}"},
    })
    blocks.append({"type": "divider"})

    # Account CRM context
    if account_row:
        arr = f"${float(account_row.arr):,.0f}" if account_row.arr else "N/A"
        bundle = draft_row.evidence_bundle or {}
        ctx = bundle.get("account_context", {})
        renewal_str = _renewal_proximity(ctx.get("renewal_date"))
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Account:* {account_row.name}\n"
                    f"Tier: `{account_row.tier}` · ARR: {arr} · Renewal: {renewal_str} · "
                    f"Health: {ctx.get('health_score', 'N/A')}"
                ),
            },
        })
        blocks.append({"type": "divider"})

    # Internal brief
    if draft_row.internal_brief:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Internal brief:*\n{draft_row.internal_brief}"},
        })
        blocks.append({"type": "divider"})

    # Confidence badge
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": _confidence_badge(draft_row.confidence)},
    })

    # Risks/unknowns
    bundle = draft_row.evidence_bundle or {}
    # risks_or_unknowns may be stored in evidence_bundle or we can check generator output
    # For now render from the internal_brief metadata if available
    if risks := bundle.get("risks_or_unknowns"):
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":warning: *Risks/unknowns:* {risks}"},
        })

    # Editable response body
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "input",
        "block_id": "response_body",
        "label": {"type": "plain_text", "text": "Response to send"},
        "element": {
            "type": "plain_text_input",
            "action_id": "response_body_value",
            "multiline": True,
            "max_length": 3000,
            "initial_value": draft_row.customer_draft or "",
        },
    })

    # Source citations
    sources = bundle.get("sources", [])
    if sources:
        blocks.append({"type": "divider"})
        citation_lines = ["*Sources:*"]
        for i, src in enumerate(sources[:10], 1):
            stale_flag = " :warning: stale" if src.get("stale") else ""
            url = src.get("url")
            link = f"<{url}|{src.get('title', 'Source')}>" if url else src.get("title", "Source")
            citation_lines.append(
                f"{i}. {link} [{src.get('provider', '')}]{stale_flag}\n"
                f"   _{src.get('excerpt', '')[:150]}…_"
            )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(citation_lines)},
        })

    # Action buttons
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Regenerate"},
                "action_id": "relay_regenerate_draft",
                "value": str(draft_row.id),
                "style": "default",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Discard"},
                "action_id": "relay_discard_draft",
                "value": str(draft_row.id),
                "style": "danger",
            },
        ],
    })

    return {
        "type": "modal",
        "callback_id": "relay_send_draft",
        "private_metadata": private_metadata,
        "title": {"type": "plain_text", "text": "Review Draft"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }
