from relay.crypto import decrypt_token, encrypt_token
from scripts.reencrypt_workspace_tokens_kms import _reencrypt_optional_secret, _reencrypt_secret

OLD_KEY = bytes.fromhex("a" * 64)
NEW_KEY = bytes.fromhex("b" * 64)


def test_reencrypt_secret_moves_plaintext_to_new_key():
    ciphertext, nonce = encrypt_token("xoxb-old", OLD_KEY)

    new_ciphertext, new_nonce = _reencrypt_secret(ciphertext, nonce, OLD_KEY, NEW_KEY)

    assert decrypt_token(new_ciphertext, new_nonce, NEW_KEY) == "xoxb-old"


def test_reencrypt_optional_secret_preserves_empty_values():
    assert _reencrypt_optional_secret(None, None, OLD_KEY, NEW_KEY) == (None, None)
