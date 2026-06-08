"""SLA polling task — runs every 60 seconds via Celery Beat.

Finds questions due for an alert, sends DM cards, records Alert rows.

Architecture note:
  Phase 1 (cross-tenant): SELECT only (id, workspace_id) with no RLS context.
  Phase 2 (per-tenant):   Open a workspace-scoped session per question so that
                          the Question ORM object is session-attached — all
                          attribute mutations commit with the session.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)

# Default alert interval when no SLA policy is configured
_DEFAULT_RESPONSE_MINUTES = 60
_DEFAULT_ESCALATION_MINUTES = 240


@celery.task(name="relay.poll_sla")
def poll_sla() -> None:
    """Entry point called by Celery Beat every 60 seconds."""
    asyncio.run(_poll_sla_async())


async def _poll_sla_async() -> None:
    from sqlalchemy import select

    from relay.config import get_settings
    from relay.db.models import Question
    from relay.db.session import get_session

    settings = get_settings()
    now = datetime.now(UTC)

    # Phase 1 — cross-tenant scan.
    # No workspace context = no RLS filter, but we only read (id, workspace_id)
    # tuples; no tenant data crosses the boundary.
    async with get_session() as session:
        result = await session.execute(
            select(Question.id, Question.workspace_id).where(
                Question.state.in_(["open", "claimed"]),
                (Question.next_alert_at.is_(None)) | (Question.next_alert_at <= now),
            )
        )
        due = result.all()  # list of Row(id, workspace_id)

    if not due:
        logger.debug("poll_sla: no questions due for alerting")
        return

    logger.info("poll_sla: %d questions due for alerting", len(due))

    for row in due:
        try:
            await _alert_question(
                question_id=row.id,
                workspace_id=row.workspace_id,
                now=now,
                settings=settings,
            )
        except Exception:
            logger.exception("poll_sla: failed to process question %s", row.id)
            # Continue — one failure must not block the rest of the batch


async def _alert_question(
    *,
    question_id: uuid.UUID,
    workspace_id: uuid.UUID,
    now: datetime,
    settings: object,
) -> None:
    """Send a DM alert for one question inside a single workspace-scoped session.

    All reads AND writes (Question update + Alert insert) happen in the same
    session so they commit atomically and the Question object is always attached.
    """
    from slack_sdk.web.async_client import AsyncWebClient
    from sqlalchemy import select

    from relay.crypto import decrypt_token, kms_provider_from_settings, workspace_encryption_key
    from relay.db.models import (
        Alert,
        CustomerAccount,
        MonitoredChannel,
        Question,
        SlaPolicy,
        Snooze,
        User,
        WorkspaceToken,
        Workspace,
    )
    from relay.db.session import get_session
    from relay.sla.alerts import build_alert_blocks

    async with get_session(workspace_id) as session:
        # Load the question inside the workspace session so it is attached
        # and all attribute changes will be committed when the session exits.
        question = await session.get(Question, question_id)
        if question is None:
            return  # deleted between scan and now

        # 1. Check for active snooze — advance next_alert_at and bail
        snooze_result = await session.execute(
            select(Snooze).where(
                Snooze.question_id == question_id,
                Snooze.snoozed_until > now,
            )
        )
        active_snooze = snooze_result.scalar_one_or_none()
        if active_snooze is not None:
            question.next_alert_at = active_snooze.snoozed_until  # persisted ✓
            return

        # 2. Dedup — skip if alerted in the last 5 minutes
        recent_cutoff = now - timedelta(minutes=5)
        dedup_result = await session.execute(
            select(Alert).where(
                Alert.question_id == question_id,
                Alert.sent_at >= recent_cutoff,
            )
        )
        if dedup_result.scalar_one_or_none() is not None:
            logger.debug("poll_sla: skipping question %s — alerted recently", question_id)
            return

        # 3. Load channel + account
        channel = await session.get(MonitoredChannel, question.channel_id)
        if channel is None:
            logger.warning("poll_sla: channel not found for question %s", question_id)
            return

        account = await session.get(CustomerAccount, question.account_id)
        if account is None:
            logger.warning("poll_sla: account not found for question %s", question_id)
            return

        # 4. Determine recipient (primary owner first alert, backup on escalation)
        is_escalation = question.alert_count > 0
        recipient_user_id: uuid.UUID | None = (
            account.backup_owner_user_id
            if (is_escalation and account.backup_owner_user_id)
            else account.owner_user_id
        )

        if recipient_user_id is None:
            logger.warning("poll_sla: no owner for question %s account %s", question_id, account.id)
            question.next_alert_at = now + timedelta(minutes=_DEFAULT_RESPONSE_MINUTES)
            return

        # 5. Load recipient user
        recipient_user = await session.get(User, recipient_user_id)
        if recipient_user is None:
            logger.warning("poll_sla: user %s not found for question %s", recipient_user_id, question_id)
            return

        if recipient_user.is_ooo:
            logger.info("poll_sla: recipient %s is OOO, skipping question %s", recipient_user.slack_user_id, question_id)
            return

        # 6. Load SLA policy for window sizes
        response_minutes = _DEFAULT_RESPONSE_MINUTES
        escalation_minutes = _DEFAULT_ESCALATION_MINUTES
        if account.sla_policy_id:
            policy = await session.get(SlaPolicy, account.sla_policy_id)
            if policy:
                response_minutes = policy.response_window_minutes
                escalation_minutes = policy.escalation_window_minutes

        sla_deadline = (
            question.created_at + timedelta(minutes=response_minutes)
            if question.created_at
            else None
        )

        # 7. Decrypt bot token
        token_result = await session.execute(
            select(WorkspaceToken).where(
                WorkspaceToken.workspace_id == workspace_id,
                WorkspaceToken.token_type == "bot",
                WorkspaceToken.is_revoked.is_(False),
            )
        )
        token_row = token_result.scalar_one_or_none()
        if token_row is None:
            logger.error("poll_sla: no active bot token for workspace %s", workspace_id)
            return

        key = settings.token_encryption_key_bytes
        kms_provider = kms_provider_from_settings(settings)
        if kms_provider is not None:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            workspace = workspace_result.scalar_one()
            key = workspace_encryption_key(workspace, key, kms_provider)

        bot_token = decrypt_token(
            token_row.encrypted_token,
            token_row.encrypted_token_nonce,
            key,
        )

        # 8. Build Block Kit card and send DM
        blocks = build_alert_blocks(
            question_id=question.id,
            title_excerpt=question.title_excerpt or "(no excerpt)",
            account_name=account.name,
            account_tier=account.tier or "unknown",
            created_at=question.created_at or now,
            sla_deadline=sla_deadline,
            alert_count=question.alert_count,
        )

        client = AsyncWebClient(token=bot_token)
        try:
            await client.chat_postMessage(
                channel=recipient_user.slack_user_id,
                text=f"🔔 Unanswered question from {account.name}: {(question.title_excerpt or '')[:100]}",
                blocks=blocks,
            )
        except Exception as exc:
            logger.error("poll_sla: Slack DM failed for question %s: %s", question_id, exc)
            raise

        # 9. Record Alert + advance Question SLA fields — committed atomically
        session.add(Alert(
            workspace_id=workspace_id,
            question_id=question_id,
            recipient_user_id=recipient_user_id,
            alert_type="escalation" if is_escalation else "primary",
            sent_at=now,
        ))
        question.last_alert_at = now
        question.alert_count = (question.alert_count or 0) + 1
        question.next_alert_at = now + timedelta(minutes=escalation_minutes)
