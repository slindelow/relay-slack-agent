"""AES-256-GCM token encryption and KMS envelope helpers."""

import secrets
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KMSProvider(Protocol):
    key_id: str

    def wrap_key(self, plaintext_dek: bytes) -> bytes:
        """Wrap a plaintext data encryption key."""

    def unwrap_key(self, wrapped_dek: bytes) -> bytes:
        """Unwrap a data encryption key."""


class AWSKMSProvider:
    def __init__(self, key_id: str, client=None) -> None:
        self.key_id = key_id
        if client is None:
            import boto3

            client = boto3.client("kms")
        self._client = client

    def wrap_key(self, plaintext_dek: bytes) -> bytes:
        response = self._client.encrypt(KeyId=self.key_id, Plaintext=plaintext_dek)
        return response["CiphertextBlob"]

    def unwrap_key(self, wrapped_dek: bytes) -> bytes:
        response = self._client.decrypt(CiphertextBlob=wrapped_dek)
        return response["Plaintext"]


def generate_dek() -> bytes:
    return secrets.token_bytes(32)


def wrap_dek(dek: bytes, kms_client: KMSProvider) -> bytes:
    return kms_client.wrap_key(dek)


def unwrap_dek(wrapped_dek: bytes, kms_client: KMSProvider) -> bytes:
    return kms_client.unwrap_key(wrapped_dek)


def workspace_encryption_key(workspace, fallback_key: bytes, kms_client: KMSProvider | None = None) -> bytes:
    if getattr(workspace, "wrapped_dek", None) and kms_client is not None:
        return unwrap_dek(workspace.wrapped_dek, kms_client)
    return fallback_key


def ensure_workspace_dek(workspace, fallback_key: bytes, kms_client: KMSProvider | None = None) -> bytes:
    if kms_client is None:
        return fallback_key
    if getattr(workspace, "wrapped_dek", None):
        return unwrap_dek(workspace.wrapped_dek, kms_client)
    dek = generate_dek()
    workspace.wrapped_dek = wrap_dek(dek, kms_client)
    workspace.kms_key_id = kms_client.key_id
    return dek


def kms_provider_from_settings(settings) -> KMSProvider | None:
    provider_value = getattr(settings, "kms_provider", "none")
    provider = provider_value.lower() if isinstance(provider_value, str) else "none"
    if provider in {"", "none", "local"}:
        return None
    if provider == "aws":
        if not settings.kms_key_id:
            raise ValueError("KMS_KEY_ID is required when KMS_PROVIDER=aws")
        return AWSKMSProvider(settings.kms_key_id)
    raise ValueError(f"Unsupported KMS_PROVIDER: {settings.kms_provider}")


def encrypt_token(plaintext: str, master_key: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_token(ciphertext: bytes, nonce: bytes, master_key: bytes) -> str:
    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
