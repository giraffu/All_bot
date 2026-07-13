from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config import REDIS_PREFIX

PRIVATE_BOT_OWNER_AUDIENCE = "qqcc-private-bot-owner"
PRIVATE_BOT_OWNER_SCOPE = "private_bot:owner"
PRIVATE_BOT_OWNER_TICKET_TTL_SECONDS = 5 * 60
PRIVATE_BOT_OWNER_TOKEN_TTL_SECONDS = 12 * 60 * 60
ALGORITHM = "HS256"


class PrivateBotOwnerAuthError(ValueError):
    pass


def _ticket_key(ticket: str, *, redis_prefix: str) -> str:
    digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    return f"{redis_prefix}private_bot_owner_ticket:{digest}"


def _owner_secret_key(secret_override: str | None = None) -> str:
    secret = (
        secret_override
        if secret_override is not None
        else os.getenv("PRIVATE_QQCC_BOT_OWNER_JWT_SECRET", "")
    ).strip()
    if not secret:
        raise PrivateBotOwnerAuthError(
            "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET is required"
        )
    try:
        padded = secret + ("=" * (-len(secret) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise PrivateBotOwnerAuthError(
            "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET must be base64url"
        ) from exc
    if len(decoded) != 32:
        raise PrivateBotOwnerAuthError(
            "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET must decode to 32 bytes"
        )

    reused_secrets = {
        os.getenv("PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY", "").strip(),
        os.getenv("QQCC_CONFIG_SECRET_KEY", "").strip(),
        os.getenv("JWT_SECRET_KEY", "").strip(),
    }
    raw_keyring = os.getenv("PRIVATE_QQCC_BOT_TOKEN_KEYRING", "").strip()
    if raw_keyring:
        try:
            keyring = json.loads(raw_keyring)
            if isinstance(keyring, dict):
                reused_secrets.update(
                    str(value).strip() for value in keyring.values()
                )
        except json.JSONDecodeError:
            pass
    reused_secrets.discard("")
    for candidate in reused_secrets:
        reused = secret == candidate
        if not reused:
            try:
                candidate_padded = candidate + ("=" * (-len(candidate) % 4))
                reused = (
                    base64.urlsafe_b64decode(candidate_padded.encode("ascii"))
                    == decoded
                )
            except Exception:
                reused = False
        if reused:
            raise PrivateBotOwnerAuthError(
                "PRIVATE_QQCC_BOT_OWNER_JWT_SECRET must not reuse another service key"
            )
    return secret


async def issue_private_bot_owner_ticket(
    *,
    internal_user_id: int,
    redis,
    redis_prefix: str = REDIS_PREFIX,
) -> str:
    if int(internal_user_id) <= 0:
        raise PrivateBotOwnerAuthError("a valid owner is required")
    for _attempt in range(3):
        ticket = secrets.token_urlsafe(32)
        created = await redis.set(
            _ticket_key(ticket, redis_prefix=redis_prefix),
            str(int(internal_user_id)),
            ex=PRIVATE_BOT_OWNER_TICKET_TTL_SECONDS,
            nx=True,
        )
        if created:
            return ticket
    raise PrivateBotOwnerAuthError("could not issue a unique owner ticket")


async def exchange_private_bot_owner_ticket(
    *,
    ticket: str,
    redis,
    secret_key: str | None = None,
    redis_prefix: str = REDIS_PREFIX,
) -> dict[str, str | int]:
    normalized = ticket.strip()
    if not normalized:
        raise PrivateBotOwnerAuthError("owner ticket is invalid or expired")
    raw_owner_id = await redis.getdel(
        _ticket_key(normalized, redis_prefix=redis_prefix)
    )
    try:
        internal_user_id = int(raw_owner_id or 0)
    except (TypeError, ValueError) as exc:
        raise PrivateBotOwnerAuthError("owner ticket is invalid or expired") from exc
    if internal_user_id <= 0:
        raise PrivateBotOwnerAuthError("owner ticket is invalid or expired")

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(internal_user_id),
        "aud": PRIVATE_BOT_OWNER_AUDIENCE,
        "scope": PRIVATE_BOT_OWNER_SCOPE,
        "iat": now,
        "exp": now + timedelta(seconds=PRIVATE_BOT_OWNER_TOKEN_TTL_SECONDS),
    }
    access_token = jwt.encode(
        payload,
        _owner_secret_key(secret_key),
        algorithm=ALGORITHM,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": PRIVATE_BOT_OWNER_TOKEN_TTL_SECONDS,
    }


def decode_private_bot_owner_token(
    token: str,
    *,
    secret_key: str | None = None,
) -> int:
    try:
        payload = jwt.decode(
            token,
            _owner_secret_key(secret_key),
            algorithms=[ALGORITHM],
            audience=PRIVATE_BOT_OWNER_AUDIENCE,
        )
    except JWTError as exc:
        raise PrivateBotOwnerAuthError("owner token is invalid") from exc
    if payload.get("scope") != PRIVATE_BOT_OWNER_SCOPE:
        raise PrivateBotOwnerAuthError("owner token has an invalid scope")
    try:
        owner_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError) as exc:
        raise PrivateBotOwnerAuthError("owner token is invalid") from exc
    if owner_id <= 0:
        raise PrivateBotOwnerAuthError("owner token is invalid")
    return owner_id
