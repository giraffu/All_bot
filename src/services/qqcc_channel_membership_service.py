from __future__ import annotations

import asyncio
import logging
import os
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import Bot

from config import REDIS_PREFIX, REQUIRED_CHANNEL_ID
from src.services.private_qqcc_bot_telegram_transport import (
    build_private_telegram_bot_base_url,
    resolve_private_telegram_file_base_url,
)
from src.services.telegram_runtime_bootstrap import build_telegram_httpx_request

logger = logging.getLogger(__name__)

QQCC_CHANNEL_MEMBERSHIP_CHECKER_KEY = "qqcc_channel_membership_checker"
DEFAULT_MEMBERSHIP_CACHE_TTL_SECONDS = 60
DEFAULT_NEGATIVE_MEMBERSHIP_CACHE_TTL_SECONDS = 5

ChannelMembershipChecker = Callable[[int], Awaitable[bool | None]]


def _normalize_cached_status(value: Any) -> bool | None:
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="ignore")
    if value == "1":
        return True
    if value == "0":
        return False
    return None


class OfficialQqccChannelMembershipChecker:
    """Shared official-Bot membership transport for every private QQCC tenant.

    The official token stays encapsulated in the worker-owned ``Bot`` instance.
    Tenant Applications receive only this callable, and Redis coalesces repeated
    checks for the same Telegram user across all tenants.
    """

    def __init__(
        self,
        bot: Any,
        *,
        redis: Any | None,
        redis_prefix: str = REDIS_PREFIX,
        cache_ttl_seconds: int = DEFAULT_MEMBERSHIP_CACHE_TTL_SECONDS,
        negative_cache_ttl_seconds: int = DEFAULT_NEGATIVE_MEMBERSHIP_CACHE_TTL_SECONDS,
        initialize_bot: bool = True,
    ) -> None:
        self._bot = bot
        self._redis = redis
        self._redis_prefix = redis_prefix
        self._cache_ttl_seconds = max(1, int(cache_ttl_seconds))
        self._negative_cache_ttl_seconds = max(1, int(negative_cache_ttl_seconds))
        self._initialize_bot = bool(initialize_bot)
        self._initialized = not self._initialize_bot
        self._initialization_lock = asyncio.Lock()
        self._membership_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def _cache_key(self, telegram_user_id: int) -> str:
        return f"{self._redis_prefix}qqcc:channel-membership:{int(telegram_user_id)}"

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._initialization_lock:
            if self._initialized:
                return
            await self._bot.initialize()
            self._initialized = True

    async def _read_cached_status(self, cache_key: str) -> bool | None:
        if self._redis is None:
            return None
        try:
            return _normalize_cached_status(await self._redis.get(cache_key))
        except Exception as exc:
            logger.warning(
                "QQCC channel membership cache read failed error_type=%s",
                type(exc).__name__,
            )
            return None

    async def __call__(self, telegram_user_id: int) -> bool | None:
        if not REQUIRED_CHANNEL_ID:
            return None

        telegram_user_id = int(telegram_user_id)
        cache_key = self._cache_key(telegram_user_id)
        cached = await self._read_cached_status(cache_key)
        if cached is not None:
            return cached

        membership_lock = self._membership_locks.get(telegram_user_id)
        if membership_lock is None:
            membership_lock = asyncio.Lock()
            self._membership_locks[telegram_user_id] = membership_lock

        async with membership_lock:
            cached = await self._read_cached_status(cache_key)
            if cached is not None:
                return cached

            await self._ensure_initialized()
            from src.utils import get_user_channel_status

            status = await get_user_channel_status(self._bot, telegram_user_id)
            if status is not None and self._redis is not None:
                try:
                    await self._redis.setex(
                        cache_key,
                        (
                            self._cache_ttl_seconds
                            if status
                            else self._negative_cache_ttl_seconds
                        ),
                        "1" if status else "0",
                    )
                except Exception as exc:
                    logger.warning(
                        "QQCC channel membership cache write failed error_type=%s",
                        type(exc).__name__,
                    )
            return status

    async def close(self) -> None:
        if not self._initialize_bot or not self._initialized:
            return
        await self._bot.shutdown()
        self._initialized = False


def build_official_qqcc_channel_membership_checker(
    *,
    redis: Any | None,
    redis_prefix: str = REDIS_PREFIX,
) -> OfficialQqccChannelMembershipChecker:
    token = (os.getenv("QQCC_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "Official QQCC Bot credential is required for private Bot membership checks"
        )

    # Every httpx/httpcore logger (including descendants) must redact Bot API
    # paths because Telegram embeds the credential in the URL.
    from src.services.private_qqcc_bot_telegram_gateway import (
        _install_http_client_token_log_guard,
    )

    _install_http_client_token_log_guard()
    request = build_telegram_httpx_request(connection_pool_size=8)
    bot = Bot(
        token=token,
        base_url=build_private_telegram_bot_base_url(),
        base_file_url=resolve_private_telegram_file_base_url(),
        request=request,
        get_updates_request=request,
    )
    token = ""
    return OfficialQqccChannelMembershipChecker(
        bot,
        redis=redis,
        redis_prefix=redis_prefix,
        initialize_bot=True,
    )
