"""SLA polling task — runs every 60 seconds via Celery Beat.

Finds questions due for an alert, sends DM cards, records Alert rows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)

# Default alert interval if no SLA policy found
_DEFAULT_RESPONSE_MINUTES = 60
_DEFAULT_ESCALATION_MINUTES = 240


@celery.task(name="relay.poll_sla")
def poll_sla() -> None:
    """Entry point called by Celery Beat every 60 seconds."""
    asyncio.run(_poll_sla_async())


async def _poll_sla_async() -> None:
    from sqlalchemy import select, text

    from relay.db.models import (
        Alert,
        CustomerAccount,
        MonitoredChannel,
        Question,
        Snooze,
        SlaPolicy,
        User,
        Workspace,
        WorkspaceToken,
    )
    from relay.db.session import get_session
    from relay.config import get_settings
    from relay.crypto import decrypt_token
    from relay.sla.alerts import build_alert_blocks

    settings = get_settings()
    now = datetime.now(UTC)

    # ------------------------------------------------------------------
    # 1. Fetch all due questions — NO workspace context (cross-tenant scan)
    # ------------------------------------------------------------------
    async with get_session() as session:
        # Turn off RLS for the poller's superuser-style cross-tenant read.
        # The poller is a trusted internal service; it does not expose tenant
        # data to other tenants — each alert is sent to the correct recipient.
        result = await session.execute(
            select(Question).where(
                Question.state.in_(["open", "claimed"]),
                (Question.next_alert_at.is_(None)) | (Question.next_alert_at <= now),
            )
        )
        due_questions = result.scalars().all()

    if not due_questions:
        logger.debug("poll_sla: no questions due for alerting")
        return

    logger.info("poll_sla: %d questions due for alerting", len(due_questions))

    for question in due_questions:
        try:
            await _alert_question(
                question=question,
                now=now,
                settings=settings,
                decrypt_token=decrypt_token,
                build_alert_blocks=build_alert_blocks,
            )
        except Exception:
            logger.exception("poll_sla: failed to process question %s", question.id)
            # Continue to next question — don't let one failure block others


async def _alert_question(
    *,
    question: "Question",
    now: datetime,
    settings: object,
    decrypt_token: object,
    build_alert_blocks: object,
) -> None:
    """Load context, send DM, record Alert, update Question for one question."""
    from slack_sdk.web.async_client import AsyncWebClient
    from sqlalchemy import select

    from relay.db.models import (
        Alert,
        CustomerAccount,
        MonitoredChannel,
        Snooze,
        SlaPolicy,
        User,
        WorkspaceToken,
    )
    from relay.db.session import get_session

    workspace_id = question.workspace_id

    async with get_session(workspace_id) as session:
        # ------------------------------------------------------------------
        # 2. Check for active snooze — skip if snoozed
        # ------------------------------------------------------------------
        snooze_result = await session.execute(
            select(Snooze).where(
                Snooze.question_id == question.id,
                Snooze.snoozed_until > now,
            )
        )
        active_snooze = snooze_result.scalar_one_or_none()
        if active_snooze is not None:
            # Update next_alert_at to when snooze lifts
            question.next_alert_at = active_snooze.snoozed_until
            return

        # ------------------------------------------------------------------
        # 3. Dedup — skip if an alert was sent in the last 5 minutes
        # ------------------------------------------------------------------
        recent_cutoff = now - timedelta(minutes=5)
        dedup_result = await session.execute(
            select(Alert).where(
                Alert.question_id == question.id,
                Alert.sent_at >= recent_cutoff,
            )
        )
        if dedup_result.scalar_one_or_none() is not None:
            logger.debug("poll_sla: skipping question %s — alerted recently", question.id)
            return

        # ------------------------------------------------------------------
        # 4. Load account + channel context
        # ------------------------------------------------------------------
        channel_result = await session.execute(
            select(MonitoredChannel).where(MonitoredChannel.id == question.channel_id)
        )
        channel = channel_result.scalar_one_or_none()
        if channel is None:
            logger.warning("poll_sla: channel not found for question %s", question.id)
            return

        account_result = await session.execute(
            select(CustomerAccount).where(CustomerAccount.id == question.account_id)
        )
        account = account_result.scalar_one_or_none()
        if account is None:
            logger.warning("poll_sla: account not found for question %s", question.id)
            return

        # ------------------------------------------------------------------
        # 5. Determine recipient — primary owner on first alert, backup after
        # ------------------------------------------------------------------
        is_escalation = question.alert_count > 0
        recipient_user_id: uuid.UUID | None = None
        if is_escalation and account.backup_owner_user_id:
            recipient_user_id = account.backup_owner_user_id
        elif account.owner_user_id:
            recipient_user_id = account.owner_user_id

        if recipient_user_id is None:
            logger.warning("poll_sla: no owner for question %s account %s", question.id, account.id)
            # Still advance next_alert_at to avoid hammering
            question.next_alert_at = now + timedelta(minutes=_DEFAULT_RESPONSE_MINUTES)
            return

        # ------------------------------------------------------------------
        # 6. Load recipient's Slack user ID
        # ------------------------------------------------------------------
        user_result = await session.execute(
            select(User).where(User.id == recipient_user_id)
        )
        recipient_user = user_result.scalar_one_or_none()
        if recipient_user is None:
            logger.warning("poll_sla: user %s not found for question %s", recipient_user_id, question.id)
            return

        # Skip if user is OOO
        if recipient_user.is_ooo:
            logger.info("poll_sla: recipient %s is OOO, skipping question %s", recipient_user.slack_user_id, question.id)
            return

        # ------------------------------------------------------------------
        # 7. Load SLA policy for next_alert_at calculation
        # ------------------------------------------------------------------
        response_minutes = _DEFAULT_RESPONSE_MINUTES
        escalation_minutes = _DEFAULT_ESCALATION_MINUTES
        if account.sla_policy_id:
            policy_result = await session.execute(
                select(SlaPolicy).where(SlaPolicy.id == account.sla_policy_id)
            )
            policy = policy_result.scalar_one_or_none()
            if policy:
                response_minutes = policy.response_window_minutes
                escalation_minutes = policy.escalation_window_minutes

        sla_deadline = (
            question.created_at + timedelta(minutes=response_minutes)
            if question.created_at
            else None
        )

        # ------------------------------------------------------------------
        # 8. Get bot token for this workspace
        # ------------------------------------------------------------------
        token_result = await session.execute(
            select(WorkspaceToken).where(
                WorkspaceToken.workspace_id == workspace_id,
                WorkspaceToken.token_type == "bot",
                WorkspaceToken.revoked_at.is_(None),
            )
        )
        token_row = token_result.scalar_one_or_none()
        if token_row is None:
            logger.error("poll_sla: no active bot token for workspace %s", workspace_id)
            return

        bot_token = decrypt_token(
            token_row.encrypted_token,
            token_row.encrypted_token_nonce,
            settings.token_encryption_key_bytes,
        )

        # ------------------------------------------------------------------
        # 9. Build Block Kit card
        # ------------------------------------------------------------------
        blocks = build_alert_blocks(
            question_id=question.id,
            title_excerpt=question.title_excerpt or "(no excerpt)",
            account_name=account.name if hasattr(account, "name") else "Unknown",
            account_tier=account.tier or "unknown",
            created_at=question.created_at or now,
            sla_deadline=sla_deadline,
            alert_count=question.alert_count,
        )

        # ------------------------------------------------------------------
        # 10. Send DM via Slack Web API
        # ------------------------------------------------------------------
        client = AsyncWebClient(token=bot_token)
        try:
            await client.chat_postMessage(
                channel=recipient_user.slack_user_id,  # DM to user
                text=f"🔔 Unanswered question from {account.name if hasattr(account, 'name') else 'customer'}: {(question.title_excerpt or '')[:100]}",
                blocks=blocks,
            )
        except Exception as exc:
            logger.error("poll_sla: Slack DM failed for question %s: %s", question.id, exc)
            raise

        # ------------------------------------------------------------------
        # 11. Record Alert row
        # ------------------------------------------------------------------
        session.add(Alert(
            workspace_id=workspace_id,
            question_id=question.id,
            recipient_user_id=recipient_user_id,
            alert_type="escalation" if is_escalation else "primary",
            sent_at=now,
        ))

        # ------------------------------------------------------------------
        # 12. Update Question SLA fields
        # ------------------------------------------------------------------
        question.last_alert_at = now
        question.alert_count = (question.alert_count or 0) + 1
        question.next_alert_at = now + timedelta(minutes=escalation_minutes)
