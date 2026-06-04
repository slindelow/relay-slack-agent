import pytest

from relay.crypto import decrypt_token, encrypt_token

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

