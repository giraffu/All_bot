import pytest
from jose import jwt

from dashboard.backend.private_bot_owner_auth import (
    PRIVATE_BOT_OWNER_AUDIENCE,
    PrivateBotOwnerAuthError,
    exchange_private_bot_owner_ticket,
    issue_private_bot_owner_ticket,
)

OWNER_SECRET = "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


class _FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex, nx):
        if nx and key in self.values:
            return False
        self.values[key] = (str(value), ex)
        return True

    async def getdel(self, key):
        entry = self.values.pop(key, None)
        return entry[0] if entry else None


@pytest.mark.asyncio
async def test_private_bot_owner_ticket_is_single_use_and_issues_scoped_token():
    redis = _FakeRedis()
    ticket = await issue_private_bot_owner_ticket(
        internal_user_id=42,
        redis=redis,
        redis_prefix="test_",
    )

    result = await exchange_private_bot_owner_ticket(
        ticket=ticket,
        redis=redis,
        secret_key=OWNER_SECRET,
        redis_prefix="test_",
    )
    claims = jwt.decode(
        result["access_token"],
        OWNER_SECRET,
        algorithms=["HS256"],
        audience=PRIVATE_BOT_OWNER_AUDIENCE,
    )

    assert claims["sub"] == "42"
    assert claims["scope"] == "private_bot:owner"
    assert result["token_type"] == "bearer"
    assert result["expires_in"] == 12 * 60 * 60

    with pytest.raises(PrivateBotOwnerAuthError):
        await exchange_private_bot_owner_ticket(
            ticket=ticket,
            redis=redis,
            secret_key=OWNER_SECRET,
            redis_prefix="test_",
        )


@pytest.mark.asyncio
async def test_private_bot_owner_ticket_rejects_empty_or_unknown_values():
    redis = _FakeRedis()

    for ticket in ("", "not-issued"):
        with pytest.raises(PrivateBotOwnerAuthError):
            await exchange_private_bot_owner_ticket(
                ticket=ticket,
                redis=redis,
                secret_key=OWNER_SECRET,
                redis_prefix="test_",
            )


def test_private_bot_owner_jwt_rejects_weak_or_reused_keys(monkeypatch):
    from src.services.private_qqcc_bot_owner_auth import _owner_secret_key

    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_JWT_SECRET", "short")
    with pytest.raises(PrivateBotOwnerAuthError):
        _owner_secret_key()

    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_JWT_SECRET", OWNER_SECRET)
    monkeypatch.setenv("PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY", OWNER_SECRET)
    with pytest.raises(PrivateBotOwnerAuthError, match="must not reuse"):
        _owner_secret_key()
