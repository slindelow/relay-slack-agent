"""AES-256-GCM token encryption + KMS envelope encryption."""

import abc
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Legacy per-field encryption (global key) — still used as fallback
# ---------------------------------------------------------------------------

def encrypt_token(plaintext: str, master_key: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_token(ciphertext: bytes, nonce: bytes, master_key: bytes) -> str:
    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# DEK-based encryption (envelope encryption)
# ---------------------------------------------------------------------------

def generate_dek() -> bytes:
    """Generate a 256-bit data encryption key."""
    return secrets.token_bytes(32)


def encrypt_with_dek(plaintext: str, dek: bytes) -> tuple[bytes, bytes]:
    """Encrypt plaintext using the provided DEK. Returns (ciphertext, nonce)."""
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_with_dek(ciphertext: bytes, nonce: bytes, dek: bytes) -> str:
    """Decrypt ciphertext using the provided DEK."""
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# KMS provider abstraction
# ---------------------------------------------------------------------------

class KMSProvider(abc.ABC):
    """Abstract KMS provider for wrapping/unwrapping DEKs."""

    @abc.abstractmethod
    def wrap_dek(self, dek: bytes) -> bytes:
        """Wrap (encrypt) a DEK with the KMS master key. Returns wrapped bytes."""

    @abc.abstractmethod
    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Unwrap (decrypt) a wrapped DEK. Returns the raw DEK bytes."""

    @abc.abstractmethod
    def key_id(self) -> str:
        """Return an identifier for the master key (stored on the workspace row)."""


class LocalKMSProvider(KMSProvider):
    """Local KMS provider for development and testing.

    Wraps the DEK with AES-256-GCM using a local key (the existing
    TOKEN_ENCRYPTION_KEY). This is NOT secure for production use but is
    identical in interface to the AWS KMS provider, making local tests valid.
    """

    def __init__(self, local_key: bytes) -> None:
        self._local_key = local_key

    def wrap_dek(self, dek: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(self._local_key)
        ciphertext = aesgcm.encrypt(nonce, dek, None)
        return nonce + ciphertext

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        nonce = wrapped_dek[:12]
        ciphertext = wrapped_dek[12:]
        aesgcm = AESGCM(self._local_key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def key_id(self) -> str:
        return "local"


def get_kms_provider() -> KMSProvider:
    """Return the configured KMS provider (local for dev/test)."""
    from relay.config import get_settings
    settings = get_settings()
    return LocalKMSProvider(settings.token_encryption_key_bytes)
