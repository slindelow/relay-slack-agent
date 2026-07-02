"""Governed context service used by MCP tools and RELAY reasoning paths."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from relay.connectors.retrieval import retrieve
from relay.context.contracts import AccountContext, ContextSource, EvidenceBundle, QuestionContext
from relay.context.slack_rts import SlackRTSClient, SlackSearchNotConnected
from relay.db.models import (
    ContextToolLog,
    CustomerAccount,
    Message,
    MonitoredChannel,
    Question,
    SourceConnector,
    SourceDocument,
    User,
)

_STALE_HOURS = 48
_TOKEN_BUDGET = 8000


def _count_tokens(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _is_stale(freshness_ts: datetime | None) -> bool:
    if freshness_ts is None:
        return True
    return (datetime.now(UTC) - freshness_ts) > timedelta(hours=_STALE_HOURS)


def _source_priority(provider: str) -> int:
    return {
        "crm": 0,
        "relay_memory": 1,
        "slack_rts": 2,
        "github": 3,
        "google_drive": 4,
        "knowledge_entry": 5,
        "retrieval": 6,
    }.get(provider, 9)


def _query_hash(query: str | None) -> str | None:
    if not query:
        return None
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


async def _actor_user_id(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_slack_user_id: str | None,
) -> uuid.UUID | None:
    if not actor_slack_user_id:
        return None
    result = await session.execute(
        select(User.id).where(
            User.workspace_id == workspace_id,
            User.slack_user_id == actor_slack_user_id,
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def log_context_tool_call(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_name: str,
    actor_slack_user_id: str | None = None,
    query: str | None = None,
    source_count: int = 0,
    question_id: uuid.UUID | None = None,
    draft_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        ContextToolLog(
            workspace_id=workspace_id,
            actor_user_id=await _actor_user_id(session, workspace_id, actor_slack_user_id),
            actor_slack_user_id=actor_slack_user_id,
            tool_name=tool_name,
            query_hash=_query_hash(query),
            source_count=source_count,
            question_id=question_id,
            draft_id=draft_id,
            metadata_json=metadata or {},
        )
    )


async def get_question_context(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    session: AsyncSession,
    *,
    actor_slack_user_id: str | None = None,
) -> QuestionContext:
    result = await session.execute(
        select(Question, Message, MonitoredChannel)
        .join(Message, Question.message_id == Message.id)
        .join(MonitoredChannel, Question.channel_id == MonitoredChannel.id)
        .where(
            Question.workspace_id == workspace_id,
            Question.id == question_id,
            Message.workspace_id == workspace_id,
            MonitoredChannel.workspace_id == workspace_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise ValueError(f"Question {question_id} not found")
    question, message, channel = row
    context = QuestionContext(
        question_id=question.id,
        account_id=question.account_id,
        channel_id=question.channel_id,
        message_id=question.message_id,
        slack_channel_id=channel.slack_channel_id,
        slack_channel_name=channel.slack_channel_name,
        slack_message_ts=message.slack_message_ts,
        slack_thread_ts=message.slack_thread_ts,
        question_excerpt=(message.raw_excerpt or question.title_excerpt or "")[:500],
        title_excerpt=question.title_excerpt,
        urgency=question.urgency,
        state=question.state,
        is_slack_connect_channel=bool(channel.is_ext_shared),
    )
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=actor_slack_user_id,
        tool_name="get_question_context",
        source_count=1,
        question_id=question_id,
    )
    return context


async def get_account_context(
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    session: AsyncSession,
    *,
    actor_slack_user_id: str | None = None,
) -> AccountContext:
    owner_alias = User
    backup_alias = User
    result = await session.execute(
        select(CustomerAccount)
        .where(
            CustomerAccount.workspace_id == workspace_id,
            CustomerAccount.id == account_id,
            CustomerAccount.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    owner_slack_user_id = None
    backup_owner_slack_user_id = None
    if account.owner_user_id:
        owner_result = await session.execute(
            select(owner_alias.slack_user_id).where(
                owner_alias.workspace_id == workspace_id,
                owner_alias.id == account.owner_user_id,
                owner_alias.deleted_at.is_(None),
            )
        )
        owner_slack_user_id = owner_result.scalar_one_or_none()
    if account.backup_owner_user_id:
        backup_result = await session.execute(
            select(backup_alias.slack_user_id).where(
                backup_alias.workspace_id == workspace_id,
                backup_alias.id == account.backup_owner_user_id,
                backup_alias.deleted_at.is_(None),
            )
        )
        backup_owner_slack_user_id = backup_result.scalar_one_or_none()

    context = AccountContext(
        account_id=account.id,
        name=account.name,
        tier=account.tier,
        arr=float(account.arr) if account.arr is not None else None,
        renewal_date=account.renewal_date.isoformat() if account.renewal_date else None,
        health_score=account.health_score,
        lifecycle_stage=account.lifecycle_stage,
        external_crm_url=account.external_crm_url,
        owner_slack_user_id=owner_slack_user_id,
        backup_owner_slack_user_id=backup_owner_slack_user_id,
        account_context=account.account_context or {},
    )
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=actor_slack_user_id,
        tool_name="get_account_context",
        source_count=1,
        metadata={"account_id": str(account_id)},
    )
    return context


async def search_indexed_knowledge(
    workspace_id: uuid.UUID,
    query: str,
    session: AsyncSession,
    *,
    top_k: int = 5,
    draft_id: uuid.UUID | None = None,
    actor_slack_user_id: str | None = None,
) -> list[ContextSource]:
    chunks = await retrieve(
        workspace_id,
        query,
        session,
        top_k=top_k,
        draft_id=draft_id,
    )
    source_doc_ids = {chunk.source_document_id for chunk in chunks if chunk.source_document_id is not None}
    docs_by_id: dict[uuid.UUID, tuple[SourceDocument, str]] = {}
    if source_doc_ids:
        docs_result = await session.execute(
            select(SourceDocument, SourceConnector.connector_type)
            .join(
                SourceConnector,
                (SourceDocument.workspace_id == SourceConnector.workspace_id)
                & (SourceDocument.connector_id == SourceConnector.id),
            )
            .where(
                SourceDocument.workspace_id == workspace_id,
                SourceDocument.id.in_(source_doc_ids),
            )
        )
        docs_by_id = {doc.id: (doc, connector_type) for doc, connector_type in docs_result.all()}

    sources: list[ContextSource] = []
    for chunk in chunks:
        citation = chunk.citation or {}
        doc_row = docs_by_id.get(chunk.source_document_id) if chunk.source_document_id else None
        doc = doc_row[0] if doc_row else None
        connector_type = doc_row[1] if doc_row else None
        provider = citation.get("provider") or connector_type or "retrieval"
        updated_at = citation.get("updated_at") or (doc.provider_updated_at.isoformat() if doc and doc.provider_updated_at else None)
        freshness_ts = _parse_ts(updated_at)
        sources.append(
            ContextSource(
                title=citation.get("title") or (doc.title if doc else "Retrieved source"),
                provider=provider,
                url=citation.get("url") or (doc.url if doc else None),
                excerpt=chunk.content[:600],
                freshness_ts=freshness_ts,
                stale=bool(citation.get("stale", _is_stale(freshness_ts))),
                visibility="customer_safe",
            )
        )
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=actor_slack_user_id,
        tool_name="search_indexed_knowledge",
        query=query,
        source_count=len(sources),
        draft_id=draft_id,
    )
    return sources


async def search_slack_context(
    workspace_id: uuid.UUID,
    acting_slack_user_id: str,
    query: str,
    session: AsyncSession,
    *,
    top_k: int = 5,
    channel_filter: list[str] | None = None,
    rts_client: SlackRTSClient | None = None,
) -> list[ContextSource]:
    client = rts_client or SlackRTSClient()
    excluded_channel_ids = await _registered_slack_connect_channel_ids(session, workspace_id)
    try:
        sources = await client.search_internal_context(
            session,
            workspace_id=workspace_id,
            acting_slack_user_id=acting_slack_user_id,
            query=query,
            top_k=top_k,
            channel_filter=channel_filter,
            exclude_channel_ids=excluded_channel_ids,
        )
        error = None
    except SlackSearchNotConnected:
        sources = []
        error = "not_connected"
    except Exception:
        sources = []
        error = "slack_api_error"
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=acting_slack_user_id,
        tool_name="search_slack_context",
        query=query,
        source_count=len(sources),
        metadata={
            "channel_filter": channel_filter or [],
            "excluded_channel_count": len(excluded_channel_ids),
            **({"error": error} if error else {}),
        },
    )
    return sources


async def search_customer_history(
    workspace_id: uuid.UUID,
    query: str,
    session: AsyncSession,
    *,
    top_k: int = 10,
    actor_slack_user_id: str | None = None,
) -> list[ContextSource]:
    result = await session.execute(
        select(Message.raw_excerpt, MonitoredChannel.slack_channel_name, Message.created_at)
        .join(
            MonitoredChannel,
            (Message.workspace_id == MonitoredChannel.workspace_id)
            & (Message.channel_id == MonitoredChannel.id),
        )
        .where(
            Message.workspace_id == workspace_id,
            Message.is_customer_message.is_(True),
            MonitoredChannel.workspace_id == workspace_id,
            MonitoredChannel.is_ext_shared.is_(True),
            MonitoredChannel.is_active.is_(True),
        )
        .order_by(desc(Message.created_at))
        .limit(top_k)
    )
    rows = result.all()
    lines: list[str] = []
    newest: datetime | None = None
    for excerpt, channel_name, created_at in rows:
        clean = " ".join(str(excerpt or "").split())
        if not clean:
            continue
        channel_prefix = f"#{channel_name}: " if channel_name else ""
        lines.append(f"- {channel_prefix}{clean[:240]}")
        if newest is None or (created_at and created_at > newest):
            newest = created_at
    sources = []
    if lines:
        sources.append(
            ContextSource(
                title="Recent registered customer-channel messages",
                provider="customer_history",
                url=None,
                excerpt="\n".join(lines),
                freshness_ts=newest,
                stale=False,
                visibility="customer_safe",
            )
        )
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=actor_slack_user_id,
        tool_name="search_customer_history",
        query=query,
        source_count=len(sources),
        metadata={"message_count": len(rows)},
    )
    return sources


async def _registered_slack_connect_channel_ids(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> set[str]:
    result = await session.execute(
        select(MonitoredChannel.slack_channel_id).where(
            MonitoredChannel.workspace_id == workspace_id,
            MonitoredChannel.is_ext_shared.is_(True),
            MonitoredChannel.is_active.is_(True),
        )
    )
    return {channel_id for channel_id in result.scalars() if channel_id}


async def assemble_evidence_for_question(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    session: AsyncSession,
    *,
    acting_slack_user_id: str | None = None,
    draft_id: uuid.UUID | None = None,
    rts_client: SlackRTSClient | None = None,
) -> EvidenceBundle:
    question = await get_question_context(
        workspace_id,
        question_id,
        session,
        actor_slack_user_id=acting_slack_user_id,
    )
    account = await get_account_context(
        workspace_id,
        question.account_id,
        session,
        actor_slack_user_id=acting_slack_user_id,
    )
    sources: list[ContextSource] = []

    if question.question_excerpt:
        try:
            sources.extend(
                await search_indexed_knowledge(
                    workspace_id,
                    question.question_excerpt,
                    session,
                    top_k=8,
                    draft_id=draft_id,
                    actor_slack_user_id=acting_slack_user_id,
                )
            )
        except Exception:
            pass
        if acting_slack_user_id:
            sources.extend(
                await search_slack_context(
                    workspace_id,
                    acting_slack_user_id,
                    question.question_excerpt,
                    session,
                    top_k=5,
                    channel_filter=None,
                    rts_client=rts_client,
                )
            )

    deduped = _dedupe_sources(sources)
    deduped.sort(key=lambda source: (
        _source_priority(source.provider),
        -(source.freshness_ts.timestamp() if source.freshness_ts else 0),
    ))
    kept, total_tokens = _enforce_token_budget(question.question_excerpt, deduped)
    await log_context_tool_call(
        session,
        workspace_id=workspace_id,
        actor_slack_user_id=acting_slack_user_id,
        tool_name="assemble_evidence_for_question",
        query=question.question_excerpt,
        source_count=len(kept),
        question_id=question_id,
        draft_id=draft_id,
    )
    return EvidenceBundle(
        question_excerpt=question.question_excerpt,
        account_context=account.to_prompt_dict(),
        sources=kept,
        total_tokens=total_tokens,
        question_context=question,
    )


def _dedupe_sources(sources: list[ContextSource]) -> list[ContextSource]:
    seen: set[str] = set()
    deduped: list[ContextSource] = []
    for source in sources:
        key = f"{source.provider}:{source.url or source.title}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _enforce_token_budget(question_excerpt: str, sources: list[ContextSource]) -> tuple[list[ContextSource], int]:
    total = _count_tokens(question_excerpt)
    kept: list[ContextSource] = []
    for source in sources:
        source_tokens = _count_tokens(source.excerpt)
        if total + source_tokens > _TOKEN_BUDGET:
            break
        total += source_tokens
        kept.append(source)
    return kept, total
