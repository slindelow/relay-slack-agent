"""Smoke-test configured KMS envelope encryption without touching customer data."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from os import environ
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from relay.crypto import (
    decrypt_token,
    encrypt_token,
    generate_dek,
    kms_provider_from_settings,
    unwrap_dek,
    wrap_dek,
)


@dataclass(frozen=True)
class SmokeResult:
    provider: str
    key_id: str
    ok: bool


def run_smoke(settings=None) -> SmokeResult:
    settings = settings or SimpleNamespace(
        kms_provider=environ.get("KMS_PROVIDER", ""),
        kms_key_id=environ.get("KMS_KEY_ID", ""),
    )
    provider = kms_provider_from_settings(settings)
    if provider is None:
        # Local/none mode: verify AES-GCM encryption with a raw DEK (no KMS wrapping)
        dek = generate_dek()
        ciphertext, nonce = encrypt_token("relay-kms-smoke-token", dek)
        plaintext = decrypt_token(ciphertext, nonce, dek)
        if plaintext != "relay-kms-smoke-token":
            raise RuntimeError("AES-GCM roundtrip failed in local mode")
        return SmokeResult(provider=settings.kms_provider or "none", key_id="local", ok=True)

    dek = generate_dek()
    wrapped = wrap_dek(dek, provider)
    unwrapped = unwrap_dek(wrapped, provider)
    if unwrapped != dek:
        raise RuntimeError("KMS unwrap returned a different DEK")

    ciphertext, nonce = encrypt_token("relay-kms-smoke-token", unwrapped)
    plaintext = decrypt_token(ciphertext, nonce, dek)
    if plaintext != "relay-kms-smoke-token":
        raise RuntimeError("AES-GCM roundtrip failed after KMS unwrap")

    return SmokeResult(provider=settings.kms_provider, key_id=settings.kms_key_id, ok=True)


def main() -> int:
    try:
        result = run_smoke()
    except Exception as exc:
        print(f"KMS smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"KMS smoke ok: provider={result.provider} key_id={result.key_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
