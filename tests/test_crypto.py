from types import SimpleNamespace
from unittest.mock import patch

import pytest

from relay.crypto import (
    decrypt_token,
    ensure_workspace_dek,
    generate_dek,
    kms_provider_from_settings,
    unwrap_dek,
    wrap_dek,
    workspace_encryption_key,
    encrypt_token,
)

FAKE_KEY = bytes.fromhex("a" * 64)


def test_round_trip():
    ciphertext, nonce = encrypt_token("xoxb-test-token", FAKE_KEY)
    assert decrypt_token(ciphertext, nonce, FAKE_KEY) == "xoxb-test-token"


def test_ciphertext_differs_from_plaintext():
    ciphertext, _ = encrypt_token("xoxb-test-token", FAKE_KEY)
    assert ciphertext != b"xoxb-test-token"


def test_nonce_is_unique_each_call():
    _, nonce1 = encrypt_token("same", FAKE_KEY)
    _, nonce2 = encrypt_token("same", FAKE_KEY)
    assert nonce1 != nonce2


def test_nonce_is_12_bytes():
    _, nonce = encrypt_token("token", FAKE_KEY)
    assert len(nonce) == 12


def test_wrong_key_raises():
    ciphertext, nonce = encrypt_token("token", FAKE_KEY)
    with pytest.raises(Exception):
        decrypt_token(ciphertext, nonce, bytes.fromhex("b" * 64))


def test_tampered_ciphertext_raises():
    ciphertext, nonce = encrypt_token("token", FAKE_KEY)
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0xFF])
    with pytest.raises(Exception):
        decrypt_token(tampered, nonce, FAKE_KEY)


class FakeKMS:
    key_id = "test-key"

    def wrap_key(self, plaintext_dek: bytes) -> bytes:
        return b"wrapped:" + plaintext_dek

    def unwrap_key(self, wrapped_dek: bytes) -> bytes:
        assert wrapped_dek.startswith(b"wrapped:")
        return wrapped_dek.removeprefix(b"wrapped:")


def test_generate_dek_is_32_bytes():
    assert len(generate_dek()) == 32


def test_wrap_unwrap_dek_with_mocked_kms():
    dek = generate_dek()
    wrapped = wrap_dek(dek, FakeKMS())
    assert wrapped != dek
    assert unwrap_dek(wrapped, FakeKMS()) == dek


def test_workspace_encryption_key_falls_back_without_wrapped_dek():
    workspace = type("Workspace", (), {"wrapped_dek": None})()
    assert workspace_encryption_key(workspace, FAKE_KEY, FakeKMS()) == FAKE_KEY


def test_ensure_workspace_dek_sets_wrapped_dek():
    workspace = type("Workspace", (), {"wrapped_dek": None, "kms_key_id": None})()
    dek = ensure_workspace_dek(workspace, FAKE_KEY, FakeKMS())
    assert dek != FAKE_KEY
    assert workspace.wrapped_dek == b"wrapped:" + dek
    assert workspace.kms_key_id == "test-key"


def test_kms_provider_from_settings_returns_none_for_local_modes():
    for provider in ("", "none", "local"):
        settings = SimpleNamespace(kms_provider=provider, kms_key_id="")
        assert kms_provider_from_settings(settings) is None


def test_kms_provider_from_settings_requires_key_for_aws():
    settings = SimpleNamespace(kms_provider="aws", kms_key_id="")
    with pytest.raises(ValueError, match="KMS_KEY_ID"):
        kms_provider_from_settings(settings)


def test_kms_provider_from_settings_builds_aws_provider():
    settings = SimpleNamespace(kms_provider="aws", kms_key_id="arn:aws:kms:test")
    with patch("relay.crypto.AWSKMSProvider") as provider_cls:
        provider = kms_provider_from_settings(settings)

    provider_cls.assert_called_once_with("arn:aws:kms:test")
    assert provider is provider_cls.return_value


def test_kms_provider_from_settings_rejects_unknown_provider():
    settings = SimpleNamespace(kms_provider="gcp", kms_key_id="key")
    with pytest.raises(ValueError, match="Unsupported"):
        kms_provider_from_settings(settings)
