"""Typed context contracts shared by MCP tools, drafting, and Slack commands."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


SourceVisibility = Literal["internal", "customer_safe"]


@dataclass(frozen=True)
class AccountContext:
    account_id: uuid.UUID
    name: str
    tier: str
    arr: float | None = None
    renewal_date: str | None = None
    health_score: float | None = None
    lifecycle_stage: str | None = None
    external_crm_url: str | None = None
    owner_slack_user_id: str | None = None
    backup_owner_slack_user_id: str | None = None
    account_context: dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["account_id"] = str(self.account_id)
        return data


@dataclass(frozen=True)
class QuestionContext:
    question_id: uuid.UUID
    account_id: uuid.UUID
    channel_id: uuid.UUID
    message_id: uuid.UUID
    slack_channel_id: str
    slack_channel_name: str | None
    slack_message_ts: str
    slack_thread_ts: str | None
    question_excerpt: str
    title_excerpt: str
    urgency: str
    state: str
    is_slack_connect_channel: bool

    def to_prompt_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("question_id", "account_id", "channel_id", "message_id"):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class ContextSource:
    title: str
    provider: str
    url: str | None
    excerpt: str
    freshness_ts: datetime | None = None
    stale: bool = False
    visibility: SourceVisibility = "customer_safe"

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "provider": self.provider,
            "url": self.url,
            "excerpt": self.excerpt,
            "freshness_ts": self.freshness_ts.isoformat() if self.freshness_ts else None,
            "stale": self.stale,
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class EvidenceBundle:
    question_excerpt: str
    account_context: dict[str, Any]
    sources: list[ContextSource] = field(default_factory=list)
    total_tokens: int = 0
    question_context: QuestionContext | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "question_excerpt": self.question_excerpt,
            "account_context": self.account_context,
            "sources": [source.to_prompt_dict() for source in self.sources],
            "total_tokens": self.total_tokens,
            "question_context": self.question_context.to_prompt_dict() if self.question_context else None,
        }
