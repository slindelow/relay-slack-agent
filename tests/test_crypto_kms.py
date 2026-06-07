"""Tests for KMS envelope encryption (Plan 7 US-001)."""

import secrets

import pytest

from relay.crypto import (
    LocalKMSProvider,
    decrypt_with_dek,
    decrypt_token,
    encrypt_token,
    encrypt_with_dek,
    generate_dek,
    get_kms_provider,
)


def test_generate_dek_is_32_bytes():
    dek = generate_dek()
    assert isinstance(dek, bytes)
    assert len(dek) == 32


def test_dek_encrypt_decrypt_roundtrip():
    dek = generate_dek()
    plaintext = "super-secret-token-value"
    ciphertext, nonce = encrypt_with_dek(plaintext, dek)
    assert ciphertext != plaintext.encode()
    result = decrypt_with_dek(ciphertext, nonce, dek)
    assert result == plaintext


def test_dek_different_nonce_each_time():
    dek = generate_dek()
    _, nonce1 = encrypt_with_dek("abc", dek)
    _, nonce2 = encrypt_with_dek("abc", dek)
    assert nonce1 != nonce2


def test_local_kms_wrap_unwrap():
    local_key = secrets.token_bytes(32)
    provider = LocalKMSProvider(local_key)

    dek = generate_dek()
    wrapped = provider.wrap_dek(dek)
    assert wrapped != dek
    assert len(wrapped) > len(dek)

    unwrapped = provider.unwrap_dek(wrapped)
    assert unwrapped == dek


def test_local_kms_key_id():
    provider = LocalKMSProvider(secrets.token_bytes(32))
    assert provider.key_id() == "local"


def test_get_kms_provider_returns_local():
    provider = get_kms_provider()
    assert isinstance(provider, LocalKMSProvider)


def test_fallback_encrypt_decrypt_still_works():
    """Legacy encrypt_token/decrypt_token still work (backward compat)."""
    master_key = secrets.token_bytes(32)
    plaintext = "legacy-token-value"
    ciphertext, nonce = encrypt_token(plaintext, master_key)
    result = decrypt_token(ciphertext, nonce, master_key)
    assert result == plaintext
