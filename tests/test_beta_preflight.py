from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import beta_preflight


def _set_required_env(monkeypatch):
    values = {
        "APP_BASE_URL": "https://relay.example.com",
        "DATABASE_URL": "postgresql+asyncpg://relay:relay@db/relay",
        "REDIS_URL": "redis://redis:6379/0",
        "SLACK_CLIENT_ID": "123.abc",
        "SLACK_CLIENT_SECRET": "secret",
        "SLACK_SIGNING_SECRET": "signing",
        "TOKEN_ENCRYPTION_KEY": "a" * 64,
        "ANTHROPIC_API_KEY": "anthropic",
        "KMS_PROVIDER": "aws",
        "KMS_KEY_ID": "arn:aws:kms:region:account:key/id",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_required_env_reports_missing(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    results = beta_preflight._check_required_env()

    assert any(result.message == "APP_BASE_URL is missing" and not result.ok for result in results)


def test_required_env_enforces_aws_kms(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("KMS_PROVIDER", "none")

    results = beta_preflight._check_required_env()

    assert any(result.message == "KMS_PROVIDER must be aws for beta launch" for result in results)


def test_manifest_generated_must_match_app_base_url(tmp_path, monkeypatch):
    manifest = tmp_path / "slack-app-manifest-generated.yaml"
    manifest.write_text("request_url: https://relay.example.com/slack/events\n")
    monkeypatch.setattr(beta_preflight, "REPO_ROOT", tmp_path)

    result = beta_preflight._check_manifest_generated("https://relay.example.com")

    assert result.ok is True


def test_run_checks_can_pass_without_live_network(tmp_path, monkeypatch):
    _set_required_env(monkeypatch)
    (tmp_path / "slack-app-manifest-generated.yaml").write_text("https://relay.example.com\n")
    monkeypatch.setattr(beta_preflight, "REPO_ROOT", tmp_path)

    with patch("scripts.beta_preflight.shutil.which", return_value="/bin/tool"):
        required, optional = beta_preflight.run_checks(live=False, timeout=1)

    assert all(result.ok for result in required)
    assert optional


def test_live_checks_call_health_and_kms(tmp_path, monkeypatch):
    _set_required_env(monkeypatch)
    (tmp_path / "slack-app-manifest-generated.yaml").write_text("https://relay.example.com\n")
    monkeypatch.setattr(beta_preflight, "REPO_ROOT", tmp_path)

    with (
        patch("scripts.beta_preflight.shutil.which", return_value="/bin/tool"),
        patch("scripts.beta_preflight._check_health", return_value=beta_preflight.CheckResult(True, "health")),
        patch("scripts.beta_preflight._check_kms_smoke", return_value=beta_preflight.CheckResult(True, "kms")),
    ):
        required, _ = beta_preflight.run_checks(live=True, timeout=1)

    assert any(result.message == "health" for result in required)
    assert any(result.message == "kms" for result in required)


def test_kms_smoke_surfaces_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(beta_preflight, "REPO_ROOT", tmp_path)
    completed = SimpleNamespace(returncode=1, stdout="", stderr="KMS smoke failed")

    with patch("scripts.beta_preflight.subprocess.run", return_value=completed):
        result = beta_preflight._check_kms_smoke()

    assert result.ok is False
    assert "KMS smoke failed" in result.message


def test_optional_missing_values_render_as_warnings(monkeypatch, capsys):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    beta_preflight._print_section("Optional", beta_preflight._check_optional_env())

    output = capsys.readouterr()
    assert "[WARN] SENTRY_DSN is not set" in output.out
