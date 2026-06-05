"""SQLAlchemy ORM models for RELAY (Plan 1 + Plan 2)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Enums (Plan 2)
# ---------------------------------------------------------------------------


class CrmProvider(str, enum.Enum):
    hubspot = "hubspot"
    salesforce = "salesforce"


class QuestionState(str, enum.Enum):
    detected = "detected"
    open = "open"
    claimed = "claimed"
    resolved = "resolved"
    expired = "expired"


class QuestionUrgency(str, enum.Enum):
    critical = "critical"
    high = "high"
    normal = "normal"
    low = "low"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Plan 1 models
# ---------------------------------------------------------------------------


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slack_team_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slack_team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tokens: Mapped[list["WorkspaceToken"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    settings: Mapped["WorkspaceSettings | None"] = relationship(back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    sla_policies: Mapped[list["SlaPolicy"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    crm_connections: Mapped[list["CrmConnection"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    customer_accounts: Mapped[list["CustomerAccount"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    monitored_channels: Mapped[list["MonitoredChannel"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.id is None:
            self.id = uuid.uuid4()


class WorkspaceToken(Base):
    __tablename__ = "workspace_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_token_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workspace: Mapped[Workspace] = relationship(back_populates="tokens")


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False)
    question_confidence_threshold_open: Mapped[float] = mapped_column(Float, nullable=False, default=0.85)
    question_confidence_threshold_candidate: Mapped[float] = mapped_column(Float, nullable=False, default=0.60)
    classifier_variant: Mapped[str] = mapped_column(String(4), nullable=False, default="a")
    alert_digest_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="settings")


class SlaPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    tier_name: Mapped[str] = mapped_column(String(32), nullable=False)
    response_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("workspace_id", "tier_name", name="uq_sla_tier"),)

    workspace: Mapped[Workspace] = relationship(back_populates="sla_policies")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    slack_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    is_ooo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("workspace_id", "slack_user_id", name="uq_user_workspace"),)

    workspace: Mapped[Workspace] = relationship(back_populates="users")


class ClassificationFeedback(Base):
    __tablename__ = "classification_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    slack_message_ts: Mapped[str] = mapped_column(String(32), nullable=False)
    slack_channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    original_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    corrected_by_slack_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    correction_action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_slack_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Plan 2 models
# ---------------------------------------------------------------------------


class CrmConnection(Base):
    __tablename__ = "crm_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    crm_provider: Mapped[CrmProvider] = mapped_column(Enum(CrmProvider, name="crm_provider"), nullable=False)
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_access_token_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encrypted_refresh_token_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    __table_args__ = (UniqueConstraint("workspace_id", "crm_provider", name="uq_crm_connection_provider"),)

    workspace: Mapped[Workspace] = relationship(back_populates="crm_connections")


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crm_provider: Mapped[CrmProvider | None] = mapped_column(Enum(CrmProvider, name="crm_provider"), nullable=True)
    external_crm_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    backup_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True)
    lifecycle_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arr: Mapped[float | None] = mapped_column(Float, nullable=True)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    external_crm_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    manual_tier_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("workspace_id", "external_crm_id", "crm_provider", name="uq_account_crm"),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="customer_accounts")
    channels: Mapped[list["MonitoredChannel"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    owner_user: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])
    backup_owner_user: Mapped["User | None"] = relationship(foreign_keys=[backup_owner_user_id])


class MonitoredChannel(Base):
    __tablename__ = "monitored_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False)
    slack_channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_slack_team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_ext_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("workspace_id", "slack_channel_id", name="uq_channel_workspace"),)

    workspace: Mapped[Workspace] = relationship(back_populates="monitored_channels")
    account: Mapped[CustomerAccount] = relationship(back_populates="channels")
    registered_by_user: Mapped["User | None"] = relationship(foreign_keys=[registered_by_user_id])


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False)
    slack_message_ts: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_slack_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_slack_team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_customer_message: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_variant: Mapped[str | None] = mapped_column(String(4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("workspace_id", "channel_id", "slack_message_ts", name="uq_message_ts"),
    )

    workspace: Mapped[Workspace] = relationship()
    channel: Mapped[MonitoredChannel] = relationship()
    question: Mapped["Question | None"] = relationship(back_populates="message", uselist=False)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitored_channels.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[QuestionState] = mapped_column(Enum(QuestionState, name="question_state"), nullable=False, default=QuestionState.detected)
    urgency: Mapped[QuestionUrgency] = mapped_column(Enum(QuestionUrgency, name="question_urgency"), nullable=False, default=QuestionUrgency.normal)
    title_excerpt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('detected', 'open', 'claimed', 'resolved', 'expired')",
            name="ck_questions_state",
        ),
        CheckConstraint(
            "urgency IN ('low', 'normal', 'high', 'critical')",
            name="ck_questions_urgency",
        ),
    )

    workspace: Mapped[Workspace] = relationship()
    channel: Mapped[MonitoredChannel] = relationship()
    message: Mapped["Message | None"] = relationship(back_populates="question")
    account: Mapped["CustomerAccount | None"] = relationship()
    events: Mapped[list["QuestionEvent"]] = relationship(back_populates="question", cascade="all, delete-orphan")


class QuestionEvent(Base):
    __tablename__ = "question_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship()
    question: Mapped[Question] = relationship(back_populates="events")
    actor_user: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])
