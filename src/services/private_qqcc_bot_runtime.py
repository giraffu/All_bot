from __future__ import annotations

import asyncio
import os
import secrets
import time
from contextlib import asynccontextmanager

from sqlalchemy import select

from config import REDIS_PREFIX
from src.services.private_qqcc_bot_credentials import PrivateBotCredentialCipher
from src.services.private_qqcc_bot_service import (
    PrivateQqccBotLifecycleService,
    PrivateBotConflictError,
    PrivateBotServiceError,
    SqlAlchemyPrivateBotRepository,
    build_private_bot_client_type,
)
from src.services.private_qqcc_bot_telegram_gateway import (
    TelegramHttpPrivateBotGateway,
)
from src.services.qqcc_demo_media_service import (
    clone_qqcc_config_demo_media_for_private_bot,
    delete_qqcc_private_bot_demo_media,
)
from src.services.task_registry import TaskRegistry
from src.services.redis_client import redis_client
from src.database.core import AsyncSessionLocal
from src.database.models import PrivateQqccBot
from src.services.private_qqcc_continuation_service import (
    private_bot_has_nonterminal_continuations,
)


PRIVATE_BOT_OPERATION_LOCK_TTL_SECONDS = 5 * 60
PRIVATE_BOT_ADMISSION_LOCK_TTL_SECONDS = 5 * 60
PRIVATE_BOT_ADMISSION_LOCK_WAIT_SECONDS = 30.0
_RELEASE_OPERATION_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
_RENEW_OPERATION_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


@asynccontextmanager
async def _redis_renewing_lock(
    *,
    redis,
    key: str,
    wait_seconds: float,
    ttl_seconds: int,
    unavailable_code: str,
    unavailable_message: str,
    conflict_code: str,
    conflict_message: str,
):
    lease = secrets.token_urlsafe(24)
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while True:
        try:
            acquired = await redis.set(
                key,
                lease,
                ex=max(1, int(ttl_seconds)),
                nx=True,
            )
        except Exception as exc:
            raise PrivateBotServiceError(
                unavailable_code,
                unavailable_message,
            ) from exc
        if acquired:
            break
        if time.monotonic() >= deadline:
            raise PrivateBotConflictError(conflict_code, conflict_message)
        await asyncio.sleep(0.05)

    owner_task = asyncio.current_task()
    stop_renewal = asyncio.Event()
    lease_lost = asyncio.Event()

    async def renew() -> None:
        renewal_seconds = max(0.1, float(ttl_seconds) / 3)
        while not stop_renewal.is_set():
            try:
                await asyncio.wait_for(
                    stop_renewal.wait(),
                    timeout=renewal_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                renewed = await redis.eval(
                    _RENEW_OPERATION_LOCK_SCRIPT,
                    1,
                    key,
                    lease,
                    str(max(1, int(ttl_seconds))),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                renewed = 0
            if int(renewed or 0) != 1:
                lease_lost.set()
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
                return

    renewal_task = asyncio.create_task(
        renew(),
        name="private-qqcc-redis-lock-renewal",
    )
    try:
        yield
        if lease_lost.is_set():
            raise PrivateBotServiceError(unavailable_code, unavailable_message)
    except asyncio.CancelledError:
        if lease_lost.is_set():
            raise PrivateBotServiceError(
                unavailable_code,
                unavailable_message,
            ) from None
        raise
    finally:
        stop_renewal.set()
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        try:
            await redis.eval(_RELEASE_OPERATION_LOCK_SCRIPT, 1, key, lease)
        except Exception:
            # Never delete a successor's lease; expiry is the final fallback.
            pass


@asynccontextmanager
async def private_bot_operation_lock(
    owner_user_id: int,
    *,
    redis=None,
    ttl_seconds: int = PRIVATE_BOT_OPERATION_LOCK_TTL_SECONDS,
):
    redis = redis if redis is not None else redis_client.redis
    key = f"{REDIS_PREFIX}private_qqcc_bot:operation:{int(owner_user_id)}"
    async with _redis_renewing_lock(
        redis=redis,
        key=key,
        wait_seconds=0,
        ttl_seconds=ttl_seconds,
        unavailable_code="operation_lock_unavailable",
        unavailable_message="Private Bot operation coordination is unavailable",
        conflict_code="operation_in_progress",
        conflict_message="Another private Bot operation is already in progress",
    ):
        yield


@asynccontextmanager
async def private_bot_admission_lock(
    private_bot_id: int,
    *,
    redis=None,
    wait_seconds: float = PRIVATE_BOT_ADMISSION_LOCK_WAIT_SECONDS,
    ttl_seconds: int = PRIVATE_BOT_ADMISSION_LOCK_TTL_SECONDS,
):
    """Serialize the final task admission fence with lifecycle state changes."""

    redis = redis if redis is not None else redis_client.redis
    key = f"{REDIS_PREFIX}private_qqcc_bot:admission:{int(private_bot_id)}"
    async with _redis_renewing_lock(
        redis=redis,
        key=key,
        wait_seconds=wait_seconds,
        ttl_seconds=ttl_seconds,
        unavailable_code="admission_lock_unavailable",
        unavailable_message="Private Bot task admission is temporarily unavailable",
        conflict_code="admission_in_progress",
        conflict_message="Private Bot task admission is busy; please retry",
    ):
        yield


async def private_bot_accepts_new_tasks(private_bot_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                PrivateQqccBot.owner_enabled,
                PrivateQqccBot.admin_enabled,
                PrivateQqccBot.runtime_status,
            ).where(PrivateQqccBot.id == int(private_bot_id))
        )
        row = result.one_or_none()
    return bool(
        row
        and row.owner_enabled
        and row.admin_enabled
        and row.runtime_status == "active"
    )


async def private_bot_exists_for_continuation(private_bot_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PrivateQqccBot.id).where(
                PrivateQqccBot.id == int(private_bot_id)
            )
        )
        return result.scalar_one_or_none() is not None


async def private_bot_has_active_tasks(private_bot_id: int) -> bool:
    client_type = build_private_bot_client_type(private_bot_id)
    tasks = await TaskRegistry.get_all_tasks_strict()
    if any(task.get("client_type") == client_type for task in tasks.values()):
        return True
    return await private_bot_has_nonterminal_continuations(private_bot_id)


def build_private_qqcc_bot_lifecycle_service(session):
    async def clone_config(source_config: dict, private_bot_id: int) -> dict:
        return await clone_qqcc_config_demo_media_for_private_bot(
            source_config,
            private_bot_id=private_bot_id,
        )

    async def cleanup_media(private_bot_id: int) -> None:
        await delete_qqcc_private_bot_demo_media(private_bot_id)

    return PrivateQqccBotLifecycleService(
        repository=SqlAlchemyPrivateBotRepository(session),
        telegram_gateway=TelegramHttpPrivateBotGateway(),
        credential_cipher=PrivateBotCredentialCipher.from_environment(),
        fingerprint_secret=os.getenv("PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY"),
        webhook_base_url=os.getenv("PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL", ""),
        active_task_checker=private_bot_has_active_tasks,
        config_cloner=clone_config,
        operation_lock=private_bot_operation_lock,
        admission_lock=private_bot_admission_lock,
        tenant_media_cleanup=cleanup_media,
    )
