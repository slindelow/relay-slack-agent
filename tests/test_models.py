from relay.db.models import (
    AuditLog,
    ClassificationFeedback,
    CrmConnection,
    CustomerAccount,
    Draft,
    DraftStatus,
    FeedbackSignal,
    ImpactMetric,
    KnowledgeChunk,
    Message,
    MonitoredChannel,
    Question,
    QuestionEvent,
    QuestionState,
    RetrievalLog,
    SlaPolicy,
    SourceConnector,
    SourceDocument,
    User,
    Workspace,
    WorkspaceSettings,
    WorkspaceToken,
)


def test_workspace_has_distinct_slack_team_id_and_internal_uuid():
    workspace = Workspace(slack_team_id="T12345", slack_team_name="Acme")
    assert workspace.id is not None
    assert workspace.slack_team_id == "T12345"
    assert str(workspace.id) != "T12345"


def test_all_tenant_tables_have_workspace_id():
    for model in (
        WorkspaceToken,
        WorkspaceSettings,
        SlaPolicy,
        User,
        CrmConnection,
        CustomerAccount,
        MonitoredChannel,
        Message,
        Question,
        QuestionEvent,
        SourceConnector,
        SourceDocument,
        KnowledgeChunk,
        Draft,
        RetrievalLog,
        FeedbackSignal,
        ImpactMetric,
        ClassificationFeedback,
        AuditLog,
    ):
        assert "workspace_id" in {column.key for column in model.__table__.columns}


def test_audit_log_has_soc2_attribution_fields():
    cols = {column.key for column in AuditLog.__table__.columns}
    required = {
        "workspace_id",
        "actor_user_id",
        "actor_ip",
        "user_agent",
        "event_type",
        "entity_type",
        "entity_id",
        "created_at",
        "old_value",
        "new_value",
    }
    assert required.issubset(cols)


def test_workspace_settings_has_configurable_thresholds():
    cols = {column.key for column in WorkspaceSettings.__table__.columns}
    assert "question_confidence_threshold_open" in cols
    assert "question_confidence_threshold_candidate" in cols


def test_sla_policy_stores_tier_windows():
    cols = {column.key for column in SlaPolicy.__table__.columns}
    assert "tier_name" in cols
    assert "response_window_minutes" in cols
    assert "escalation_window_minutes" in cols


def test_classification_feedback_captures_correction_action():
    cols = {column.key for column in ClassificationFeedback.__table__.columns}
    assert "correction_action" in cols
    assert "corrected_label" in cols
    assert "original_confidence" in cols


def test_crm_connection_is_unique_by_provider_per_workspace():
    constraints = {constraint.name for constraint in CrmConnection.__table__.constraints}
    assert "uq_crm_connection_provider" in constraints
    cols = {column.key for column in CrmConnection.__table__.columns}
    assert "hubspot_portal_id" in cols
    assert "access_token_expires_at" in cols


def test_customer_account_has_crm_and_ownership_fields():
    cols = {column.key for column in CustomerAccount.__table__.columns}
    required = {
        "crm_provider",
        "external_crm_id",
        "owner_user_id",
        "backup_owner_user_id",
        "sla_policy_id",
        "tier",
        "arr",
        "renewal_date",
        "health_score",
        "manual_tier_override",
        "account_context",
        "deleted_at",
    }
    assert required.issubset(cols)


def test_monitored_channel_stores_customer_workspace_identity():
    cols = {column.key for column in MonitoredChannel.__table__.columns}
    assert "slack_channel_id" in cols
    assert "customer_slack_team_id" in cols
    assert "is_ext_shared" in cols
    assert "is_active" in cols


def test_message_has_slack_idempotency_and_classifier_fields():
    cols = {column.key for column in Message.__table__.columns}
    required = {
        "slack_message_ts",
        "is_customer_message",
        "raw_excerpt",
        "classification_label",
        "classification_confidence",
        "classification_variant",
    }
    assert required.issubset(cols)


def test_message_has_unique_constraint_on_ts():
    constraint_names = {c.name for c in Message.__table__.constraints}
    assert "uq_message_slack_ts" in constraint_names


def test_question_state_enum_has_five_states():
    states = {s.value for s in QuestionState}
    assert states == {"detected", "open", "claimed", "resolved", "expired"}


def test_question_has_visible_state_machine_and_sla_fields():
    cols = {column.key for column in Question.__table__.columns}
    required = {
        "state",
        "next_alert_at",
        "last_alert_at",
        "alert_count",
        "snoozed_until",
        "urgency",
        "title_excerpt",
        "resolved_at",
    }
    assert required.issubset(cols)
    constraints = {constraint.name for constraint in Question.__table__.constraints}
    assert "ck_questions_state" in constraints
    assert "ck_questions_urgency" in constraints


def test_question_event_uses_metadata_column_safely():
    assert hasattr(QuestionEvent, "event_metadata")
    assert "metadata" in QuestionEvent.__table__.columns


def test_plan2_models_have_tenant_scoped_fk_constraints():
    expected = {
        CustomerAccount: {
            "fk_customer_owner_same_workspace",
            "fk_customer_backup_owner_same_workspace",
            "fk_customer_sla_policy_same_workspace",
            "uq_customer_account_workspace_id",
        },
        MonitoredChannel: {
            "fk_channel_account_same_workspace",
            "fk_channel_registered_by_same_workspace",
            "uq_monitored_channel_workspace_id",
        },
        Message: {"fk_message_channel_same_workspace", "uq_message_workspace_id"},
        Question: {
            "fk_question_channel_same_workspace",
            "fk_question_message_same_workspace",
            "fk_question_account_same_workspace",
            "uq_question_workspace_id",
        },
        QuestionEvent: {
            "fk_question_event_question_same_workspace",
            "fk_question_event_actor_same_workspace",
        },
    }
    for model, names in expected.items():
        constraint_names = {constraint.name for constraint in model.__table__.constraints}
        assert names.issubset(constraint_names)


def test_plan4_source_models_have_connector_and_retrieval_fields():
    connector_cols = {column.key for column in SourceConnector.__table__.columns}
    assert {
        "connector_type",
        "config",
        "encrypted_credentials",
        "encrypted_credentials_nonce",
        "sync_status",
        "last_synced_at",
        "disconnected_at",
    }.issubset(connector_cols)

    document_cols = {column.key for column in SourceDocument.__table__.columns}
    assert {
        "connector_id",
        "external_id",
        "title",
        "url",
        "config",
        "content_hash",
        "provider_updated_at",
        "last_synced_at",
    }.issubset(document_cols)

    chunk_cols = {column.key for column in KnowledgeChunk.__table__.columns}
    assert {
        "source_document_id",
        "knowledge_entry_id",
        "chunk_index",
        "content",
        "embedding",
        "embedding_model",
        "embedding_dims",
        "content_hash",
    }.issubset(chunk_cols)

    retrieval_cols = {column.key for column in RetrievalLog.__table__.columns}
    assert {"draft_id", "sources_used", "query", "retrieved_at"}.issubset(retrieval_cols)


def test_plan4_models_have_tenant_scoped_constraints():
    expected = {
        SourceConnector: {"uq_source_connector_workspace_id", "ck_source_connectors_type"},
        SourceDocument: {
            "fk_source_document_connector_same_workspace",
            "uq_source_document_external_id",
            "uq_source_document_workspace_id",
        },
        KnowledgeChunk: {
            "fk_knowledge_chunk_source_document_same_workspace",
            "uq_knowledge_chunk_workspace_id",
            "uq_knowledge_chunk_content_hash",
            "ck_knowledge_chunks_embedding_dims",
        },
        RetrievalLog: {"fk_retrieval_log_draft_same_workspace", "uq_retrieval_log_workspace_id"},
    }
    for model, names in expected.items():
        constraint_names = {constraint.name for constraint in model.__table__.constraints}
        assert names.issubset(constraint_names)


def test_knowledge_chunk_uses_pgvector_1536_embedding():
    embedding_type = KnowledgeChunk.__table__.columns["embedding"].type
    assert getattr(embedding_type, "dim", None) == 1536


def test_plan5_draft_model_has_approval_lifecycle_fields():
    cols = {column.key for column in Draft.__table__.columns}
    required = {
        "question_id",
        "evidence_bundle",
        "customer_draft",
        "internal_brief",
        "confidence",
        "status",
        "editor_user_id",
        "approved_by_user_id",
        "sent_at",
    }
    assert required.issubset(cols)
    assert {status.value for status in DraftStatus} == {"pending", "approved", "discarded", "sent"}


def test_plan5_draft_model_has_tenant_scoped_constraints():
    constraint_names = {constraint.name for constraint in Draft.__table__.constraints}
    assert {
        "fk_draft_question_same_workspace",
        "fk_draft_editor_same_workspace",
        "fk_draft_approver_same_workspace",
        "uq_draft_workspace_id",
        "ck_drafts_status",
    }.issubset(constraint_names)


def test_plan5_feedback_signal_has_prd_feedback_fields():
    cols = {column.key for column in FeedbackSignal.__table__.columns}
    assert {
        "message_id",
        "question_id",
        "draft_id",
        "actor_user_id",
        "correction_action",
        "original_label",
        "corrected_label",
        "original_confidence",
        "notes",
    }.issubset(cols)
    constraint_names = {constraint.name for constraint in FeedbackSignal.__table__.constraints}
    assert {
        "fk_feedback_message_same_workspace",
        "fk_feedback_question_same_workspace",
        "fk_feedback_draft_same_workspace",
        "fk_feedback_actor_same_workspace",
        "uq_feedback_signal_workspace_id",
        "ck_feedback_signals_action",
    }.issubset(constraint_names)


def test_plan5_impact_metric_has_prd_metric_fields():
    cols = {column.key for column in ImpactMetric.__table__.columns}
    assert {
        "account_id",
        "question_id",
        "draft_id",
        "time_to_first_alert_seconds",
        "time_to_first_draft_seconds",
        "time_to_send_seconds",
        "sla_met",
        "draft_accepted",
        "draft_edit_distance",
        "alert_to_action",
    }.issubset(cols)
    constraint_names = {constraint.name for constraint in ImpactMetric.__table__.constraints}
    assert {
        "fk_impact_metric_account_same_workspace",
        "fk_impact_metric_question_same_workspace",
        "fk_impact_metric_draft_same_workspace",
        "uq_impact_metric_workspace_id",
    }.issubset(constraint_names)
