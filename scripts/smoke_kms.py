"""Smoke-test configured KMS envelope encryption without touching customer data."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from relay.config import get_settings
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
    settings = settings or get_settings()
    provider = kms_provider_from_settings(settings)
    if provider is None:
        raise RuntimeError("KMS_PROVIDER=aws and KMS_KEY_ID are required for KMS smoke testing")

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
