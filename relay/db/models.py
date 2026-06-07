"""SQLAlchemy ORM models for RELAY (Plan 1 + Plan 2)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


# ---------------------------------------------------------------------------
# Enums (used by state machine and application code)
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


class ConnectorType(str, enum.Enum):
    google_drive = "google_drive"
    github = "github"
    notion = "notion"


class DraftStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    discarded = "discarded"
    sent = "sent"


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
    source_connectors: Mapped[list["SourceConnector"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    knowledge_entries: Mapped[list["KnowledgeEntry"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

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


class WorkspaceDeletionJob(Base):
    __tablename__ = "workspace_deletion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    actor_slack_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','complete','failed')",
            name="ck_workspace_deletion_jobs_status",
        ),
        Index("idx_workspace_deletion_jobs_workspace_created", "workspace_id", "created_at"),
    )


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

    __table_args__ = (
        UniqueConstraint("workspace_id", "tier_name", name="uq_sla_tier"),
        UniqueConstraint("workspace_id", "id", name="uq_sla_policy_workspace_id"),
    )

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

    __table_args__ = (
        UniqueConstraint("workspace_id", "slack_user_id", name="uq_user_workspace"),
        UniqueConstraint("workspace_id", "id", name="uq_user_workspace_id"),
    )

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
    crm_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="hubspot")
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_access_token_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encrypted_refresh_token_nonce: Mapped[bytes | None] = mapped_column(LargeBinary(12), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hubspot_portal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_synced")
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("workspace_id", "crm_provider", name="uq_crm_connection_provider"),)

    workspace: Mapped[Workspace] = relationship(back_populates="crm_connections")


class CustomerAccount(Base):
    __tablename__ = "customer_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_crm_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    backup_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lifecycle_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arr: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    external_crm_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_tier_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "owner_user_id"], ["users.workspace_id", "users.id"], name="fk_customer_owner_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "backup_owner_user_id"], ["users.workspace_id", "users.id"], name="fk_customer_backup_owner_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "sla_policy_id"], ["sla_policies.workspace_id", "sla_policies.id"], name="fk_customer_sla_policy_same_workspace"),
        UniqueConstraint("workspace_id", "id", name="uq_customer_account_workspace_id"),
        Index(
            "uq_customer_external_crm_id_active",
            "workspace_id",
            "crm_provider",
            "external_crm_id",
            unique=True,
            postgresql_where=(deleted_at.is_(None) & external_crm_id.is_not(None)),
        ),
        Index("idx_customer_accounts_workspace_domain", "workspace_id", "domain"),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="customer_accounts")
    monitored_channels: Mapped[list["MonitoredChannel"]] = relationship(back_populates="account", cascade="all, delete-orphan", overlaps="monitored_channels")
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])
    backup_owner: Mapped["User | None"] = relationship(foreign_keys=[backup_owner_user_id])
    sla_policy: Mapped[SlaPolicy | None] = relationship(overlaps="customer_accounts,workspace")


class MonitoredChannel(Base):
    __tablename__ = "monitored_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slack_channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    slack_channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_slack_team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_ext_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "account_id"], ["customer_accounts.workspace_id", "customer_accounts.id"], ondelete="CASCADE", name="fk_channel_account_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "registered_by_user_id"], ["users.workspace_id", "users.id"], name="fk_channel_registered_by_same_workspace"),
        UniqueConstraint("workspace_id", "slack_channel_id", name="uq_monitored_channel_workspace"),
        UniqueConstraint("workspace_id", "id", name="uq_monitored_channel_workspace_id"),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="monitored_channels", overlaps="monitored_channels")
    account: Mapped[CustomerAccount] = relationship(back_populates="monitored_channels", overlaps="monitored_channels,workspace")
    registered_by_user: Mapped["User | None"] = relationship(foreign_keys=[registered_by_user_id])
    messages: Mapped[list["Message"]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    questions: Mapped[list["Question"]] = relationship(back_populates="channel", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slack_message_ts: Mapped[str] = mapped_column(String(32), nullable=False)
    slack_thread_ts: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_slack_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sender_slack_team_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_customer_message: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    classification_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_variant: Mapped[str | None] = mapped_column(String(4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "channel_id"], ["monitored_channels.workspace_id", "monitored_channels.id"], ondelete="CASCADE", name="fk_message_channel_same_workspace"),
        UniqueConstraint("workspace_id", "channel_id", "slack_message_ts", name="uq_message_slack_ts"),
        UniqueConstraint("workspace_id", "id", name="uq_message_workspace_id"),
        Index("idx_messages_workspace_channel_ts", "workspace_id", "channel_id", "slack_message_ts"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="messages")
    channel: Mapped[MonitoredChannel] = relationship(back_populates="messages", overlaps="workspace")
    questions: Mapped[list["Question"]] = relationship(back_populates="message", cascade="all, delete-orphan", overlaps="questions")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="detected")
    urgency: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    title_excerpt: Mapped[str] = mapped_column(String(255), nullable=False)
    next_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "channel_id"], ["monitored_channels.workspace_id", "monitored_channels.id"], ondelete="CASCADE", name="fk_question_channel_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "message_id"], ["messages.workspace_id", "messages.id"], ondelete="CASCADE", name="fk_question_message_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "account_id"], ["customer_accounts.workspace_id", "customer_accounts.id"], ondelete="CASCADE", name="fk_question_account_same_workspace"),
        CheckConstraint(
            "state IN ('detected', 'open', 'claimed', 'resolved', 'expired')",
            name="ck_questions_state",
        ),
        CheckConstraint(
            "urgency IN ('low', 'normal', 'high', 'critical')",
            name="ck_questions_urgency",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_question_workspace_id"),
        Index("idx_questions_sla_check", "next_alert_at", "workspace_id", postgresql_where=state.in_(["open", "claimed"])),
        Index("idx_questions_workspace_state", "workspace_id", "state"),
    )

    # overlaps= silences SAWarning: composite FKs make workspace_id reachable via
    # multiple relationship paths. We always set workspace_id explicitly in
    # constructors — we never rely on ORM cascade to propagate it.
    workspace: Mapped[Workspace] = relationship(overlaps="questions")
    channel: Mapped[MonitoredChannel] = relationship(back_populates="questions", overlaps="questions,workspace")
    message: Mapped[Message] = relationship(back_populates="questions", overlaps="channel,questions,workspace")
    account: Mapped[CustomerAccount] = relationship(overlaps="channel,message,questions,workspace")
    events: Mapped[list["QuestionEvent"]] = relationship(back_populates="question", cascade="all, delete-orphan")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="question", cascade="all, delete-orphan")
    knowledge_entries: Mapped[list["KnowledgeEntry"]] = relationship(back_populates="question", foreign_keys="[KnowledgeEntry.question_id]", overlaps="knowledge_entries,workspace")


class QuestionEvent(Base):
    __tablename__ = "question_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "question_id"], ["questions.workspace_id", "questions.id"], ondelete="CASCADE", name="fk_question_event_question_same_workspace"),
        ForeignKeyConstraint(["workspace_id", "actor_user_id"], ["users.workspace_id", "users.id"], name="fk_question_event_actor_same_workspace"),
        Index("idx_question_events_question_created", "question_id", "created_at"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="events")
    question: Mapped[Question] = relationship(back_populates="events", overlaps="workspace")
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])


# ---------------------------------------------------------------------------
# Plan 3 models — SLA engine
# ---------------------------------------------------------------------------


class AlertType(str, enum.Enum):
    primary = "primary"
    backup = "backup"
    escalation = "escalation"


class Alert(Base):
    """Sent DM alert for a question. One row per delivery attempt."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AlertType.primary.value)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_alert_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "recipient_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_alert_recipient_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_alert_workspace_id"),
        CheckConstraint(
            "alert_type IN ('primary','backup','escalation')",
            name="ck_alerts_alert_type",
        ),
        Index("idx_alerts_question_sent", "question_id", "sent_at"),
    )

    workspace: Mapped[Workspace] = relationship()
    question: Mapped[Question] = relationship(overlaps="workspace")
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_user_id])


class Assignment(Base):
    """Question assignment record — supports re-assignment (unassigned_at is set on removal)."""

    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_assignment_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "assignee_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_assignment_assignee_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "assigned_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_assignment_assigned_by_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_assignment_workspace_id"),
        Index("idx_assignments_question_active", "question_id", postgresql_where=text("unassigned_at IS NULL")),
    )

    workspace: Mapped[Workspace] = relationship()
    question: Mapped[Question] = relationship(overlaps="workspace")
    assignee: Mapped[User] = relationship(foreign_keys=[assignee_user_id])
    assigned_by: Mapped["User | None"] = relationship(foreign_keys=[assigned_by_user_id])


class Snooze(Base):
    """Snooze record — suppress alerts for a question until snoozed_until."""

    __tablename__ = "snoozes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snoozed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    snoozed_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_snooze_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "snoozed_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_snooze_user_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_snooze_workspace_id"),
        Index("idx_snoozes_question_active", "question_id", "snoozed_until"),
    )


# ---------------------------------------------------------------------------
# Plan 4 models — source connectors and retrieval
# ---------------------------------------------------------------------------


class SourceConnector(Base):
    """Configured external knowledge source for a workspace."""

    __tablename__ = "source_connectors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_credentials_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_synced")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "connector_type IN ('google_drive','github','notion')",
            name="ck_source_connectors_type",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_source_connector_workspace_id"),
        Index("idx_source_connectors_workspace_active", "workspace_id", postgresql_where=text("disconnected_at IS NULL")),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="source_connectors")
    documents: Mapped[list["SourceDocument"]] = relationship(back_populates="connector", cascade="all, delete-orphan", overlaps="workspace")


class SourceDocument(Base):
    """One external source item, such as a Drive doc or GitHub issue."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connector_id"],
            ["source_connectors.workspace_id", "source_connectors.id"],
            ondelete="CASCADE",
            name="fk_source_document_connector_same_workspace",
        ),
        UniqueConstraint("workspace_id", "connector_id", "external_id", name="uq_source_document_external_id"),
        UniqueConstraint("workspace_id", "id", name="uq_source_document_workspace_id"),
        Index("idx_source_documents_workspace_connector", "workspace_id", "connector_id"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="documents,source_connectors")
    connector: Mapped[SourceConnector] = relationship(back_populates="documents", overlaps="workspace")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="source_document", cascade="all, delete-orphan", overlaps="workspace")


class KnowledgeChunk(Base):
    """Embedded text chunk used for semantic retrieval."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    knowledge_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dims: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "source_document_id"],
            ["source_documents.workspace_id", "source_documents.id"],
            ondelete="CASCADE",
            name="fk_knowledge_chunk_source_document_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "knowledge_entry_id"],
            ["knowledge_entries.workspace_id", "knowledge_entries.id"],
            name="fk_knowledge_chunk_entry_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_knowledge_chunk_workspace_id"),
        UniqueConstraint("workspace_id", "content_hash", name="uq_knowledge_chunk_content_hash"),
        CheckConstraint("embedding_dims = 1536", name="ck_knowledge_chunks_embedding_dims"),
        Index("idx_knowledge_chunks_workspace_source", "workspace_id", "source_document_id"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="chunks,documents,source_connectors")
    source_document: Mapped[SourceDocument | None] = relationship(back_populates="chunks", overlaps="workspace")
    knowledge_entry: Mapped["KnowledgeEntry | None"] = relationship(back_populates="chunks", foreign_keys="[KnowledgeChunk.workspace_id, KnowledgeChunk.knowledge_entry_id]", overlaps="chunks,source_document,workspace")


class Draft(Base):
    """Human-approved response draft generated from retrieved evidence."""

    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_bundle: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    customer_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_brief: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DraftStatus.pending.value)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_draft_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "editor_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_draft_editor_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approved_by_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_draft_approver_same_workspace",
        ),
        CheckConstraint(
            "status IN ('pending','approved','discarded','sent')",
            name="ck_drafts_status",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_draft_workspace_id"),
        Index("idx_drafts_workspace_question", "workspace_id", "question_id"),
        Index("idx_drafts_workspace_status", "workspace_id", "status"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="drafts")
    question: Mapped[Question] = relationship(back_populates="drafts", overlaps="workspace")
    editor: Mapped["User | None"] = relationship(foreign_keys=[editor_user_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_user_id])
    retrieval_logs: Mapped[list["RetrievalLog"]] = relationship(back_populates="draft", overlaps="workspace")


class RetrievalLog(Base):
    """Audit trail for semantic retrieval calls."""

    __tablename__ = "retrieval_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sources_used: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_retrieval_log_draft_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_retrieval_log_workspace_id"),
        Index("idx_retrieval_logs_workspace_retrieved", "workspace_id", "retrieved_at"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="draft,retrieval_logs")
    draft: Mapped["Draft | None"] = relationship(back_populates="retrieval_logs", overlaps="workspace")


# ---------------------------------------------------------------------------
# Plan 5 models — feedback signals and impact metrics
# ---------------------------------------------------------------------------


class FeedbackSignal(Base):
    """CSM correction or draft feedback signal."""

    __tablename__ = "feedback_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correction_action: Mapped[str] = mapped_column(String(64), nullable=False)
    original_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    corrected_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            name="fk_feedback_message_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            name="fk_feedback_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_feedback_draft_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_user_id"],
            ["users.workspace_id", "users.id"],
            name="fk_feedback_actor_same_workspace",
        ),
        CheckConstraint(
            "correction_action IN ('mark_not_question','mark_question','discard_draft','regenerate_draft','incorrect_source','incorrect_response')",
            name="ck_feedback_signals_action",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_feedback_signal_workspace_id"),
        Index("idx_feedback_signals_workspace_question", "workspace_id", "question_id"),
    )

    workspace: Mapped[Workspace] = relationship()


class ImpactMetric(Base):
    """Outcome metrics recorded when a draft is sent or discarded."""

    __tablename__ = "impact_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    time_to_first_alert_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_first_draft_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_send_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    draft_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    draft_edit_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alert_to_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "account_id"],
            ["customer_accounts.workspace_id", "customer_accounts.id"],
            name="fk_impact_metric_account_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_impact_metric_question_same_workspace",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["drafts.workspace_id", "drafts.id"],
            name="fk_impact_metric_draft_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_impact_metric_workspace_id"),
        Index("idx_impact_metrics_workspace_question", "workspace_id", "question_id"),
    )

    workspace: Mapped[Workspace] = relationship(overlaps="impact_metrics")


# ---------------------------------------------------------------------------
# Plan 6 models — knowledge entries (resolution memory)
# ---------------------------------------------------------------------------


class KnowledgeEntry(Base):
    """Resolved question captured as a reusable knowledge entry."""

    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_question: Mapped[str] = mapped_column(Text, nullable=False)
    internal_answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_bundle: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reuse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "question_id"],
            ["questions.workspace_id", "questions.id"],
            name="fk_knowledge_entry_question_same_workspace",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_knowledge_entry_workspace_id"),
        Index("idx_knowledge_entries_workspace_created", "workspace_id", "created_at"),
    )

    # overlaps= silences SAWarning from multiple composite FK paths back to workspace_id
    workspace: Mapped[Workspace] = relationship(back_populates="knowledge_entries", overlaps="workspace")
    question: Mapped["Question | None"] = relationship(back_populates="knowledge_entries", foreign_keys=[question_id], overlaps="workspace")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="knowledge_entry", foreign_keys="[KnowledgeChunk.workspace_id, KnowledgeChunk.knowledge_entry_id]", overlaps="chunks,source_document,workspace")
