from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PrivateBotCredentialError(ValueError):
    """Raised when private Bot credentials cannot be safely processed."""


@dataclass(frozen=True, slots=True)
class EncryptedPrivateBotToken:
    ciphertext: str
    key_version: int


def _decode_key(raw_key: str, *, label: str) -> bytes:
    try:
        padded = raw_key + ("=" * (-len(raw_key) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise PrivateBotCredentialError(f"{label} is not valid base64") from exc
    if len(decoded) != 32:
        raise PrivateBotCredentialError(f"{label} must decode to 32 bytes")
    return decoded


class PrivateBotCredentialCipher:
    """Versioned AES-GCM keyring for Telegram Bot tokens."""

    def __init__(self, *, keys: Mapping[int, bytes], active_version: int):
        normalized = {int(version): bytes(key) for version, key in keys.items()}
        if not normalized or active_version not in normalized:
            raise PrivateBotCredentialError("active credential key version is unavailable")
        if any(len(key) != 32 for key in normalized.values()):
            raise PrivateBotCredentialError("all credential keys must be 32 bytes")
        self._keys = normalized
        self.active_version = int(active_version)

    @classmethod
    def from_environment(cls) -> "PrivateBotCredentialCipher":
        raw_keyring = os.getenv("PRIVATE_QQCC_BOT_TOKEN_KEYRING", "").strip()
        if not raw_keyring:
            raise PrivateBotCredentialError(
                "PRIVATE_QQCC_BOT_TOKEN_KEYRING is required"
            )
        try:
            payload = json.loads(raw_keyring)
        except json.JSONDecodeError as exc:
            raise PrivateBotCredentialError(
                "PRIVATE_QQCC_BOT_TOKEN_KEYRING must be a JSON object"
            ) from exc
        if not isinstance(payload, dict):
            raise PrivateBotCredentialError(
                "PRIVATE_QQCC_BOT_TOKEN_KEYRING must be a JSON object"
            )
        keys: dict[int, bytes] = {}
        try:
            for raw_version, raw_key in payload.items():
                version = int(raw_version)
                if version <= 0 or version in keys:
                    raise ValueError
                keys[version] = _decode_key(
                    str(raw_key),
                    label=f"credential key {raw_version}",
                )
        except (TypeError, ValueError) as exc:
            raise PrivateBotCredentialError(
                "credential key versions must be unique positive integers"
            ) from exc
        raw_active = os.getenv("PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION", "").strip()
        try:
            active_version = int(raw_active) if raw_active else max(keys)
        except (TypeError, ValueError) as exc:
            raise PrivateBotCredentialError(
                "active credential key version is invalid"
            ) from exc
        return cls(keys=keys, active_version=active_version)

    def encrypt(self, token: str, *, associated_data: str) -> EncryptedPrivateBotToken:
        normalized = token.strip()
        if not normalized or not associated_data:
            raise PrivateBotCredentialError("token and associated data are required")
        nonce = os.urandom(12)
        encrypted = AESGCM(self._keys[self.active_version]).encrypt(
            nonce,
            normalized.encode("utf-8"),
            associated_data.encode("utf-8"),
        )
        ciphertext = base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")
        return EncryptedPrivateBotToken(
            ciphertext=ciphertext,
            key_version=self.active_version,
        )

    def decrypt(
        self,
        ciphertext: str,
        *,
        key_version: int,
        associated_data: str,
    ) -> str:
        key = self._keys.get(int(key_version))
        if key is None:
            raise PrivateBotCredentialError("credential key version is unavailable")
        try:
            decoded = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
            nonce, encrypted = decoded[:12], decoded[12:]
            if len(nonce) != 12 or not encrypted:
                raise ValueError("invalid encrypted payload")
            plaintext = AESGCM(key).decrypt(
                nonce,
                encrypted,
                associated_data.encode("utf-8"),
            )
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise PrivateBotCredentialError("private Bot token cannot be decrypted") from exc


def build_token_fingerprint(token: str, *, secret: str | None = None) -> str:
    raw_secret = (
        secret
        if secret is not None
        else os.getenv("PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY", "")
    ).strip()
    if not raw_secret:
        raise PrivateBotCredentialError(
            "PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY is required"
        )
    key = _decode_key(raw_secret, label="token fingerprint key")
    return hmac.new(key, token.strip().encode("utf-8"), hashlib.sha256).hexdigest()
