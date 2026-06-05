from relay.db.models import (
    AuditLog,
    ClassificationFeedback,
    CrmConnection,
    CustomerAccount,
    Message,
    MonitoredChannel,
    Question,
    QuestionEvent,
    QuestionState,
    SlaPolicy,
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


def test_plan2_tenant_models_have_workspace_id():
    for model in (CrmConnection, CustomerAccount, MonitoredChannel, Message, Question, QuestionEvent):
        assert "workspace_id" in {column.key for column in model.__table__.columns}, (
            f"{model.__name__} is missing workspace_id"
        )


def test_question_state_enum_has_five_states():
    states = {s.value for s in QuestionState}
    assert states == {"detected", "open", "claimed", "resolved", "expired"}


def test_monitored_channel_has_customer_slack_team_id():
    cols = {column.key for column in MonitoredChannel.__table__.columns}
    assert "customer_slack_team_id" in cols


def test_message_has_unique_constraint_on_ts():
    constraint_names = {c.name for c in Message.__table__.constraints}
    assert "uq_message_ts" in constraint_names
