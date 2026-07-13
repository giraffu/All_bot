import base64

import pytest

from src.services.private_qqcc_bot_credentials import (
    PrivateBotCredentialCipher,
    PrivateBotCredentialError,
    build_token_fingerprint,
)


def _key(byte: int) -> bytes:
    return bytes([byte]) * 32


def test_private_bot_token_round_trip_binds_ciphertext_to_bot_record():
    cipher = PrivateBotCredentialCipher(keys={1: _key(7)}, active_version=1)

    encrypted = cipher.encrypt("123456:secret-token", associated_data="bot-public-id")

    assert encrypted.key_version == 1
    assert "123456:secret-token" not in encrypted.ciphertext
    assert (
        cipher.decrypt(
            encrypted.ciphertext,
            key_version=encrypted.key_version,
            associated_data="bot-public-id",
        )
        == "123456:secret-token"
    )


def test_private_bot_token_cannot_be_decrypted_for_another_record():
    cipher = PrivateBotCredentialCipher(keys={1: _key(8)}, active_version=1)
    encrypted = cipher.encrypt("123456:secret-token", associated_data="bot-a")

    with pytest.raises(PrivateBotCredentialError):
        cipher.decrypt(
            encrypted.ciphertext,
            key_version=1,
            associated_data="bot-b",
        )


def test_private_bot_token_fingerprint_is_stable_and_does_not_expose_token():
    secret = base64.urlsafe_b64encode(_key(9)).decode()

    first = build_token_fingerprint("123456:secret-token", secret=secret)
    second = build_token_fingerprint("123456:secret-token", secret=secret)

    assert first == second
    assert len(first) == 64
    assert "secret-token" not in first
