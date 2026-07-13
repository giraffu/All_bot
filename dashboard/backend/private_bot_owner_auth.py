"""Compatibility exports for the private QQCC Bot owner-auth service."""

from src.services.private_qqcc_bot_owner_auth import (
    ALGORITHM,
    PRIVATE_BOT_OWNER_AUDIENCE,
    PRIVATE_BOT_OWNER_SCOPE,
    PRIVATE_BOT_OWNER_TICKET_TTL_SECONDS,
    PRIVATE_BOT_OWNER_TOKEN_TTL_SECONDS,
    PrivateBotOwnerAuthError,
    decode_private_bot_owner_token,
    exchange_private_bot_owner_ticket,
    issue_private_bot_owner_ticket,
)

__all__ = [
    "ALGORITHM",
    "PRIVATE_BOT_OWNER_AUDIENCE",
    "PRIVATE_BOT_OWNER_SCOPE",
    "PRIVATE_BOT_OWNER_TICKET_TTL_SECONDS",
    "PRIVATE_BOT_OWNER_TOKEN_TTL_SECONDS",
    "PrivateBotOwnerAuthError",
    "decode_private_bot_owner_token",
    "exchange_private_bot_owner_ticket",
    "issue_private_bot_owner_ticket",
]
