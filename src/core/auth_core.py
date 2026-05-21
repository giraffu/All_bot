import hashlib
import hmac
import json
import logging
import urllib.parse
import asyncio
import bcrypt
from typing import Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from src.database.core import AsyncSessionLocal
from src.core.user_core import get_or_create_user_by_telegram
from src.database.models import User
from src.services.permission_service import permission_service
from src.services.redis_client import redis_client

logger = logging.getLogger(__name__)


class AuthCoreError(Exception):
    pass


class InvalidSignatureError(AuthCoreError):
    pass


class InvalidCredentialsError(AuthCoreError):
    pass


class InsufficientPermissionError(AuthCoreError):
    pass


class RateLimitError(AuthCoreError):
    pass


CHECK_RATE_LIMIT_SCRIPT = """
local ip_key = KEYS[1]
local user_key = KEYS[2]
local max_attempts = tonumber(ARGV[1])

local ip_attempts = tonumber(redis.call('GET', ip_key) or '0')
local user_attempts = tonumber(redis.call('GET', user_key) or '0')

if ip_attempts >= max_attempts or user_attempts >= max_attempts then
    return 1
end
return 0
"""

INCR_RATE_LIMIT_SCRIPT = """
local ip_key = KEYS[1]
local user_key = KEYS[2]
local expire_time = tonumber(ARGV[1])

local ip_new = redis.call('INCR', ip_key)
if ip_new == 1 then
    redis.call('EXPIRE', ip_key, expire_time)
end

local user_new = redis.call('INCR', user_key)
if user_new == 1 then
    redis.call('EXPIRE', user_key, expire_time)
end
return 1
"""
def _verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    pre_hashed = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return bcrypt.checkpw(pre_hashed.encode("utf-8"), hashed_password.encode("utf-8"))


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        _verify_password_sync, plain_password, hashed_password
    )


def _get_password_hash_sync(password: str) -> str:
    pre_hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(pre_hashed.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_password_hash(password: str) -> str:
    return await asyncio.to_thread(_get_password_hash_sync, password)


def verify_telegram_authorization(data: dict) -> bool:
    """Verify the hash of the Telegram auth data (Widget format)."""
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    import time

    auth_date = data.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 900:
        logger.error(
            "Telegram auth_date is too old or missing (Replay attack prevention)."
        )
        return False

    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items())])

    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return False

    for token in tokens_to_try:
        secret_key = hashlib.sha256(token.encode()).digest()
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(expected_hash, received_hash):
            return True

    return False


def verify_telegram_webapp_initdata(init_data: str) -> Optional[dict]:
    """
    Verify the initData string passed from Telegram Mini App.
    Returns parsed user dict if valid, else None.
    """
    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    import time

    auth_date = params.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 900:
        logger.error("Telegram WebApp auth_date is too old or missing.")
        return None

    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(params.items())])

    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return None

    is_valid = False
    for token in tokens_to_try:
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(expected_hash, received_hash):
            is_valid = True
            break

    if not is_valid:
        return None

    user_str = params.get("user")
    if not user_str:
        return None

    try:
        return json.loads(user_str)
    except Exception as e:
        logger.error(f"Failed to parse user from initData: {e}")
        return None


async def authenticate_and_get_user(
    init_data: Optional[str] = None, widget_data: Optional[dict] = None
) -> Tuple[User, dict]:
    """
    Authenticate user via initData or widget_data, and return (user_model, stats).
    Raises InvalidSignatureError if auth fails.
    """
    if init_data:
        user_data = verify_telegram_webapp_initdata(init_data)
        if not user_data:
            raise InvalidSignatureError(
                "Invalid Telegram WebApp authentication signature."
            )

        tg_id = user_data.get("id")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        username = user_data.get("username", "")

        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()
    elif widget_data:
        if (
            not widget_data.get("id")
            or not widget_data.get("hash")
            or not widget_data.get("auth_date")
        ):
            raise InvalidSignatureError(
                "Missing required fields for Login Widget auth."
            )

        if not verify_telegram_authorization(widget_data):
            raise InvalidSignatureError("Invalid Telegram authentication signature.")

        tg_id = widget_data.get("id")
        first_name = widget_data.get("first_name", "")
        last_name = widget_data.get("last_name", "")
        username = widget_data.get("username", "")

        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()
    else:
        raise InvalidSignatureError("No authentication data provided.")

    # Initialize language_code
    language_code = None
    if init_data:
        language_code = user_data.get("language_code")
    elif widget_data:
        language_code = widget_data.get("language_code")

    user, _is_new = await get_or_create_user_by_telegram(
        tg_id=tg_id, username=username, full_name=full_name, language_code=language_code
    )

    stats = await permission_service.get_user_detailed_stats(user.telegram_id)

    return user, stats


async def authenticate_user_by_password(
    username: str, password: str, client_ip: str
) -> Tuple[User, dict]:
    redis = redis_client.redis

    # 1. Rate limiting check via Lua script
    ip_key = f"allbot:ratelimit:login:ip:{client_ip}"
    user_key = f"allbot:ratelimit:login:user:{username.lower()}"

    is_locked = await redis.eval(CHECK_RATE_LIMIT_SCRIPT, 2, ip_key, user_key, 5)
    if is_locked == 1:
        raise RateLimitError("请求过于频繁，请稍后再试。")

    async with AsyncSessionLocal() as session:
        # 2. Find user
        stmt = (
            select(User)
            .where(text("lower(username) = :uname"))
            .params(uname=username.lower())
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        # Dummy hash to prevent timing attacks
        dummy_hash = "$2b$12$xGzN6R9UuP.BvA8aH3/1/.P7f1k4uX8q9Pz7vR5n3yO1l6t9uV2.O"
        hashed_password = (
            user.hashed_password if user and user.hashed_password else dummy_hash
        )

        # 3. Verify password
        is_valid = await verify_password(password, hashed_password)

        if not user or not user.hashed_password or not is_valid:
            # Increment rate limits via Lua script (atomic)
            await redis.eval(INCR_RATE_LIMIT_SCRIPT, 2, ip_key, user_key, 900)
            raise InvalidCredentialsError("道号或密咒错误，或尝试次数过多。")

        # 4. Check web access
        if not await permission_service.check_web_access(user.id):
            raise InsufficientPermissionError(
                "权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端"
            )

        # 5. Success: clear rate limits
        await redis.delete(ip_key, user_key)

        stats = await permission_service.get_user_detailed_stats(user.telegram_id)
        return user, stats


async def bind_user_password(
    user_id: int, username: str, password: str, client_ip: str
) -> None:
    redis = redis_client.redis

    # 1. Rate limiting check via Lua script
    ip_key = f"allbot:ratelimit:bind:ip:{client_ip}"
    user_key = f"allbot:ratelimit:bind:user:{user_id}"

    is_locked = await redis.eval(CHECK_RATE_LIMIT_SCRIPT, 2, ip_key, user_key, 5)
    if is_locked == 1:
        raise RateLimitError("操作过于频繁，请稍后再试。")

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            raise AuthCoreError("用户不存在。")

        if not await permission_service.check_web_access(user.id):
            raise InsufficientPermissionError(
                "权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能绑定 Web 端账号"
            )

        # Hash password
        hashed = await get_password_hash(password)

        try:
            user.username = username
            user.hashed_password = hashed
            user.password_version += 1
            session.add(user)
            await session.flush()  # flush to catch IntegrityError before commit
        except IntegrityError:
            await session.rollback()
            # Increment rate limits on failure
            await redis.eval(INCR_RATE_LIMIT_SCRIPT, 2, ip_key, user_key, 900)
            raise AuthCoreError("道号已被其他道友占用，请重新选择。")

        await session.commit()

        # Success: clear rate limits
        await redis.delete(ip_key, user_key)

        # Optional: session invalidation via Redis blacklisting could be added here
        # block old version
        blacklist_key = f"allbot:auth:blacklist:{user.id}:{user.password_version - 1}"
        await redis.setex(blacklist_key, 604800, "1")  # 7 days
