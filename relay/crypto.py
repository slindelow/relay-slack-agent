"""AES-256-GCM token encryption."""

import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_token(plaintext: str, master_key: bytes) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_token(ciphertext: bytes, nonce: bytes, master_key: bytes) -> str:
    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")

