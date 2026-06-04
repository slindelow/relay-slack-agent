from relay.db.models import AuditLog, ClassificationFeedback, SlaPolicy, User, Workspace, WorkspaceSettings, WorkspaceToken


def test_workspace_has_distinct_slack_team_id_and_internal_uuid():
    workspace = Workspace(slack_team_id="T12345", slack_team_name="Acme")
    assert workspace.id is not None
    assert workspace.slack_team_id == "T12345"
    assert str(workspace.id) != "T12345"


def test_all_tenant_tables_have_workspace_id():
    for model in (WorkspaceToken, WorkspaceSettings, SlaPolicy, User, ClassificationFeedback, AuditLog):
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

