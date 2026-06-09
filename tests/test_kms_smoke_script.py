from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.smoke_kms import main, run_smoke


class FakeKMS:
    key_id = "kms-key"

    def wrap_key(self, plaintext_dek: bytes) -> bytes:
        return b"wrapped:" + plaintext_dek

    def unwrap_key(self, wrapped_dek: bytes) -> bytes:
        return wrapped_dek.removeprefix(b"wrapped:")


def test_run_smoke_round_trips_with_mocked_kms():
    settings = SimpleNamespace(kms_provider="aws", kms_key_id="kms-key")
    with patch("scripts.smoke_kms.kms_provider_from_settings", return_value=FakeKMS()):
        result = run_smoke(settings)

    assert result.ok is True
    assert result.provider == "aws"
    assert result.key_id == "kms-key"


def test_run_smoke_requires_kms_provider():
    settings = SimpleNamespace(kms_provider="none", kms_key_id="")
    with patch("scripts.smoke_kms.kms_provider_from_settings", return_value=None):
        with pytest.raises(RuntimeError, match="KMS_PROVIDER=aws"):
            run_smoke(settings)


def test_main_uses_kms_env_without_full_app_settings(monkeypatch, capsys):
    monkeypatch.setenv("KMS_PROVIDER", "aws")
    monkeypatch.setenv("KMS_KEY_ID", "kms-key")
    with patch("scripts.smoke_kms.kms_provider_from_settings", return_value=FakeKMS()):
        assert main() == 0

    output = capsys.readouterr()
    assert "KMS smoke ok" in output.out
    assert "key_id=kms-key" in output.out
