"""Block Kit alert card builder for SLA DM alerts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def _human_duration(delta_seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    if delta_seconds < 60:
        return f"{int(delta_seconds)}s"
    minutes = int(delta_seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def build_alert_blocks(
    *,
    question_id: uuid.UUID,
    title_excerpt: str,
    account_name: str,
    account_tier: str,
    created_at: datetime,
    sla_deadline: datetime | None,
    alert_count: int,
) -> list[dict]:
    """Build Slack Block Kit blocks for a question alert DM.

    Args:
        question_id: UUID of the question (used in action value payloads).
        title_excerpt: Short question text excerpt.
        account_name: Customer account name.
        account_tier: Tier string (enterprise, pro, starter).
        created_at: When the question was first detected.
        sla_deadline: When the SLA response window expires (None if no policy).
        alert_count: Number of alerts sent so far (0 = first alert).

    Returns:
        List of Block Kit block dicts suitable for Slack's API.
    """
    now = datetime.now(UTC)
    waiting_secs = (now - created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else now - created_at).total_seconds()
    waiting_str = _human_duration(max(0, waiting_secs))

    if sla_deadline is not None:
        deadline_secs = (sla_deadline.replace(tzinfo=UTC) if sla_deadline.tzinfo is None else sla_deadline - now).total_seconds() if sla_deadline > now else 0
        if sla_deadline > now:
            deadline_secs = (sla_deadline - now).total_seconds()
            sla_str = f"⏱ {_human_duration(deadline_secs)} remaining"
        else:
            sla_str = "🔴 SLA breached"
    else:
        sla_str = "No SLA policy"

    tier_emoji = {"enterprise": "🏢", "pro": "🥈", "starter": "🌱"}.get(account_tier.lower(), "🏢")

    escalation_note = " — *Escalation alert*" if alert_count > 0 else ""
    header = f"🔔 *Unanswered customer question*{escalation_note}"

    q_id_str = str(question_id)

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Account:*\n{tier_emoji} {account_name} ({account_tier})"},
                {"type": "mrkdwn", "text": f"*Waiting:*\n{waiting_str}"},
                {"type": "mrkdwn", "text": f"*SLA:*\n{sla_str}"},
                {"type": "mrkdwn", "text": f"*Question:*\n_{title_excerpt[:200]}_"},
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Claim"},
                    "action_id": "relay_claim_question",
                    "value": q_id_str,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Snooze 1h"},
                    "action_id": "relay_snooze_1h",
                    "value": q_id_str,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Snooze 4h"},
                    "action_id": "relay_snooze_4h",
                    "value": q_id_str,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Not a question"},
                    "action_id": "relay_mark_not_question",
                    "value": q_id_str,
                    "style": "danger",
                },
            ],
        },
        {"type": "divider"},
    ]
