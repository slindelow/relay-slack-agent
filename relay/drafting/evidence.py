"""Evidence bundle constructor for draft generation (US-002)."""

from __future__ import annotations

import uuid
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.connectors.retrieval import retrieve


@dataclass
class EvidenceSource:
    title: str
    provider: str
    url: str | None
    excerpt: str
    freshness_ts: datetime | None
    stale: bool


@dataclass
class EvidenceBundle:
    question_excerpt: str
    account_context: dict
    sources: list[EvidenceSource] = field(default_factory=list)
    total_tokens: int = 0


_STALE_HOURS = 48
_TOKEN_BUDGET = 8000


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _is_stale(freshness_ts: datetime | None) -> bool:
    if freshness_ts is None:
        return True
    return (datetime.now(UTC) - freshness_ts) > timedelta(hours=_STALE_HOURS)


def _source_priority(provider: str) -> int:
    """Lower number = higher priority."""
    return {
        "crm": 0,
        "relay_memory": 1,
        "github": 2,
        "google_drive": 3,
        "knowledge_entry": 4,
    }.get(provider, 9)


async def assemble_evidence(
    workspace_id: uuid.UUID,
    question_id: uuid.UUID,
    session: AsyncSession,
    draft_id: uuid.UUID | None = None,
) -> EvidenceBundle:
    """Gather and rerank all relevant context for a question into an EvidenceBundle."""
    from relay.db.models import CustomerAccount, Message, MonitoredChannel, Question

    q_result = await session.execute(
        select(Question, Message)
        .join(Message, Question.message_id == Message.id)
        .where(
            Question.workspace_id == workspace_id,
            Question.id == question_id,
            Message.workspace_id == workspace_id,
        )
    )
    row = q_result.one_or_none()
    if inspect.isawaitable(row):
        row = await row
    if row is None:
        raise ValueError(f"Question {question_id} not found")

    question, message = row
    question_excerpt = (message.raw_excerpt or question.title_excerpt or "")[:500]

    # Load account context from CRM data
    account_context: dict = {}
    if question and question.channel_id:
        ch_result = await session.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.workspace_id == workspace_id,
                MonitoredChannel.id == question.channel_id,
            )
        )
        channel = ch_result.scalar_one_or_none()
        if channel and channel.account_id:
            acct_result = await session.execute(
                select(CustomerAccount).where(
                    CustomerAccount.workspace_id == workspace_id,
                    CustomerAccount.id == channel.account_id,
                )
            )
            account = acct_result.scalar_one_or_none()
            if account:
                account_context = {
                    "tier": account.tier,
                    "arr": float(account.arr) if account.arr is not None else None,
                    "renewal_date": account.renewal_date.isoformat() if account.renewal_date else None,
                    "health_score": account.health_score,
                    "lifecycle_stage": account.lifecycle_stage,
                    "account_context": account.account_context or {},
                }

    sources: list[EvidenceSource] = []

    if question_excerpt:
        try:
            retrieved_chunks = await retrieve(
                workspace_id,
                question_excerpt,
                session,
                top_k=8,
                draft_id=draft_id,
            )
            for chunk in retrieved_chunks:
                cit = chunk.citation
                sources.append(EvidenceSource(
                    title=cit.get("title", "Retrieved source"),
                    provider=cit.get("provider", "retrieval"),
                    url=cit.get("url"),
                    excerpt=chunk.content[:600],
                    freshness_ts=_parse_ts(cit.get("updated_at")),
                    stale=cit.get("stale", False),
                ))
        except Exception:
            pass

    # Deduplicate by (provider, url or title)
    seen: set[str] = set()
    deduped: list[EvidenceSource] = []
    for src in sources:
        key = f"{src.provider}:{src.url or src.title}"
        if key not in seen:
            seen.add(key)
            deduped.append(src)

    # Rerank: by authority tier then freshness (most recent first)
    deduped.sort(key=lambda s: (
        _source_priority(s.provider),
        -(s.freshness_ts.timestamp() if s.freshness_ts else 0),
    ))

    # Token budget enforcement — drop lowest priority until under budget
    total = _count_tokens(question_excerpt)
    kept: list[EvidenceSource] = []
    for src in deduped:
        src_tokens = _count_tokens(src.excerpt)
        if total + src_tokens > _TOKEN_BUDGET:
            break
        total += src_tokens
        kept.append(src)

    return EvidenceBundle(
        question_excerpt=question_excerpt,
        account_context=account_context,
        sources=kept,
        total_tokens=total,
    )


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None
