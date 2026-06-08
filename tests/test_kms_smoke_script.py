from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.smoke_kms import run_smoke


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
