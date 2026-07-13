from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import signal
import socket
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from redis.exceptions import ResponseError
from sqlalchemy import select, update
from telegram import Update

from config import REDIS_PREFIX
from qqcc_bot.main import build_application
from src.database.models import PrivateQqccBot, PrivateQqccBotAuditLog
from src.services.private_qqcc_bot_credentials import PrivateBotCredentialCipher
from src.services.private_qqcc_bot_metrics import publish_private_qqcc_worker_metrics
from src.services.private_qqcc_bot_service import build_private_bot_client_type
from src.services.private_qqcc_bot_telegram_transport import (
    build_private_telegram_bot_base_url,
    resolve_private_telegram_file_base_url,
)
from src.services.qqcc_config_service import normalize_qqcc_config
from src.services.recovery_service import recover_private_bot_tasks
from src.services.zombie_cleaner_service import clean_private_qqcc_zombies
from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
)


logger = logging.getLogger("qqcc_private_bot.worker")

DEFAULT_CONSUMER_GROUP = "private-qqcc-bot-workers"
DEFAULT_CONCURRENCY = 16
DEFAULT_BATCH_SIZE = 50
DEFAULT_BLOCK_MS = 1_000
DEFAULT_PENDING_IDLE_MS = 60_000
DEFAULT_RETRY_SECONDS = 1.0
DEFAULT_PENDING_SWEEP_SECONDS = 30.0
DEFAULT_APPLICATION_IDLE_SECONDS = 5 * 60.0
DEFAULT_ADMISSION_TIMEOUT_SECONDS = 5 * 60.0
DEFAULT_ZOMBIE_SWEEP_SECONDS = 10 * 60.0
DEFAULT_METRICS_PUBLISH_SECONDS = 15.0
DEFAULT_MAX_INFLIGHT_UPDATES = 64
DEFAULT_PER_BOT_PREFETCH = 8
DEFAULT_MAX_DEFERRED_UPDATES = 1024
PROCESSED_UPDATE_TTL_SECONDS = 7 * 24 * 60 * 60
FAILED_UPDATE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_UPDATE_PROCESSING_ATTEMPTS = 3
WORKER_LEADER_TTL_SECONDS = 30
WORKER_LEADER_RENEW_SECONDS = 10.0

_ACK_AND_DELETE_SCRIPT = """
local acknowledged = redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
if acknowledged == 1 then
    redis.call('XDEL', KEYS[1], ARGV[2])
end
return acknowledged
"""
_RENEW_LEADER_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LEADER_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""
_INCREMENT_FAILURE_SCRIPT = """
local attempts = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[1])
return attempts
"""


def _positive_int_from_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_float_from_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return str(value)


@dataclass(frozen=True, slots=True)
class PrivateBotRuntimeRecord:
    private_bot_id: int
    owner_enabled: bool
    admin_enabled: bool
    runtime_status: str
    token_ciphertext: str
    token_key_version: int
    token_fingerprint: str
    webhook_public_id: str

    @property
    def is_active(self) -> bool:
        return (
            self.owner_enabled
            and self.admin_enabled
            and self.runtime_status == "active"
        )


class PrivateQqccBotStore(Protocol):
    async def get_runtime_record(
        self, private_bot_id: int
    ) -> PrivateBotRuntimeRecord | None: ...

    async def load_config(self, private_bot_id: int) -> dict[str, Any]: ...

    async def mark_update_processed(
        self,
        private_bot_id: int,
        *,
        webhook_received_at: datetime,
        processed_at: datetime,
    ) -> None: ...

    async def mark_runtime_error(
        self,
        private_bot_id: int,
        *,
        error_code: str,
        occurred_at: datetime,
        disable_runtime: bool,
    ) -> None: ...


class SqlAlchemyPrivateQqccBotStore:
    """Small DB seam used by the stream worker and its tests."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get_runtime_record(
        self, private_bot_id: int
    ) -> PrivateBotRuntimeRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PrivateQqccBot).where(PrivateQqccBot.id == int(private_bot_id))
            )
            bot = result.scalar_one_or_none()
            if bot is None:
                return None
            return PrivateBotRuntimeRecord(
                private_bot_id=int(bot.id),
                owner_enabled=bool(bot.owner_enabled),
                admin_enabled=bool(bot.admin_enabled),
                runtime_status=str(bot.runtime_status),
                token_ciphertext=str(bot.token_ciphertext),
                token_key_version=int(bot.token_key_version),
                token_fingerprint=str(bot.token_fingerprint),
                webhook_public_id=str(bot.webhook_public_id),
            )

    async def load_config(self, private_bot_id: int) -> dict[str, Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PrivateQqccBot.config).where(
                    PrivateQqccBot.id == int(private_bot_id)
                )
            )
            config = result.scalar_one_or_none()
            if not isinstance(config, dict):
                raise LookupError("private QQCC Bot config is unavailable")
            return dict(config)

    async def mark_update_processed(
        self,
        private_bot_id: int,
        *,
        webhook_received_at: datetime,
        processed_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(PrivateQqccBot)
                .where(PrivateQqccBot.id == int(private_bot_id))
                .values(
                    last_webhook_at=webhook_received_at,
                    last_update_at=processed_at,
                )
            )
            await session.commit()

    async def mark_runtime_error(
        self,
        private_bot_id: int,
        *,
        error_code: str,
        occurred_at: datetime,
        disable_runtime: bool,
    ) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PrivateQqccBot)
                .where(PrivateQqccBot.id == int(private_bot_id))
                .with_for_update()
            )
            bot = result.scalar_one_or_none()
            if bot is None:
                return
            before_status = str(bot.runtime_status)
            if disable_runtime and bot.owner_enabled and bot.admin_enabled:
                bot.runtime_status = "error"
            bot.last_error_code = error_code[:64]
            bot.last_error_message = "Private Bot runtime processing failed"
            session.add(
                PrivateQqccBotAuditLog(
                    private_bot=bot,
                    owner_user_id=bot.owner_user_id,
                    telegram_bot_id=bot.telegram_bot_id,
                    actor_type="system",
                    actor_identifier=None,
                    action=(
                        "runtime_error"
                        if disable_runtime
                        else "update_processing_failed"
                    ),
                    before_status=before_status,
                    after_status=str(bot.runtime_status),
                    details={
                        "error_code": error_code[:64],
                        "occurred_at": occurred_at.isoformat(),
                    },
                )
            )
            await session.commit()


class TelegramApplication(Protocol):
    bot: Any
    bot_data: dict[str, Any]

    async def initialize(self) -> None: ...

    async def start(self) -> None: ...

    async def process_update(self, update: Update) -> None: ...

    async def stop(self) -> None: ...

    async def shutdown(self) -> None: ...


ApplicationBuilder = Callable[..., TelegramApplication]
UpdateDecoder = Callable[[dict[str, Any], Any], Update]
RecoverTasks = Callable[[Callable[[int], Awaitable[object | None]]], Awaitable[None]]
CleanZombies = Callable[
    [Callable[[int], Awaitable[object | None]]],
    Awaitable[int],
]


@dataclass(frozen=True, slots=True)
class PrivateQqccBotWorkerDependencies:
    redis: Any
    store: PrivateQqccBotStore
    credential_cipher: PrivateBotCredentialCipher
    channel_membership_checker: Callable[[int], Awaitable[bool | None]] | None = None
    channel_membership_checker_shutdown: Callable[[], Awaitable[None]] | None = None
    application_builder: ApplicationBuilder = build_application
    update_decoder: UpdateDecoder = Update.de_json
    normalize_config: Callable[[Any], dict[str, Any]] = normalize_qqcc_config
    recover_tasks: RecoverTasks = recover_private_bot_tasks
    clean_zombies: CleanZombies = clean_private_qqcc_zombies
    now: Callable[[], datetime] = datetime.now
    monotonic: Callable[[], float] = time.monotonic


@dataclass(frozen=True, slots=True)
class WebhookStreamEntry:
    message_id: str | bytes
    private_bot_id: int
    update_id: int
    update_json: str
    received_at: datetime


@dataclass(slots=True)
class _ManagedApplication:
    application: TelegramApplication
    token_fingerprint: str
    last_used_at: float


class PrivateQqccBotWorker:
    """Consume private QQCC webhook updates with per-Bot ordering."""

    def __init__(
        self,
        dependencies: PrivateQqccBotWorkerDependencies,
        *,
        redis_prefix: str = REDIS_PREFIX,
        consumer_group: str = DEFAULT_CONSUMER_GROUP,
        consumer_name: str | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_ms: int = DEFAULT_BLOCK_MS,
        pending_idle_ms: int = DEFAULT_PENDING_IDLE_MS,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
        pending_sweep_seconds: float = DEFAULT_PENDING_SWEEP_SECONDS,
        application_idle_seconds: float = DEFAULT_APPLICATION_IDLE_SECONDS,
        admission_timeout_seconds: float = DEFAULT_ADMISSION_TIMEOUT_SECONDS,
        zombie_sweep_seconds: float = DEFAULT_ZOMBIE_SWEEP_SECONDS,
        metrics_publish_seconds: float = DEFAULT_METRICS_PUBLISH_SECONDS,
        max_inflight_updates: int = DEFAULT_MAX_INFLIGHT_UPDATES,
        per_bot_prefetch: int = DEFAULT_PER_BOT_PREFETCH,
        max_deferred_updates: int = DEFAULT_MAX_DEFERRED_UPDATES,
    ):
        self.dependencies = dependencies
        self.redis_prefix = redis_prefix
        self.stream_key = f"{redis_prefix}private_qqcc_bot:webhook:updates"
        self.leader_key = f"{redis_prefix}private_qqcc_bot:worker:leader"
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or (
            f"{socket.gethostname()}-{os.getpid()}"
        )
        self.batch_size = max(1, int(batch_size))
        self.block_ms = max(1, int(block_ms))
        self.pending_idle_ms = max(1, int(pending_idle_ms))
        self.retry_seconds = max(0.01, float(retry_seconds))
        self.pending_sweep_seconds = max(0.1, float(pending_sweep_seconds))
        self.application_idle_seconds = max(0.1, float(application_idle_seconds))
        self.admission_timeout_seconds = max(0.1, float(admission_timeout_seconds))
        self.zombie_sweep_seconds = max(1.0, float(zombie_sweep_seconds))
        self.metrics_publish_seconds = max(1.0, float(metrics_publish_seconds))
        self.max_inflight_updates = max(1, int(max_inflight_updates))
        self.per_bot_prefetch = max(
            1,
            min(int(per_bot_prefetch), self.max_inflight_updates),
        )
        self.max_deferred_updates = max(1, int(max_deferred_updates))
        self._semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self._stop_event = asyncio.Event()
        self._leader_stop_event = asyncio.Event()
        self._bot_queues: dict[int, asyncio.Queue[WebhookStreamEntry]] = {}
        self._bot_tasks: dict[int, asyncio.Task[None]] = {}
        self._applications: dict[int, _ManagedApplication] = {}
        self._application_locks: dict[int, asyncio.Lock] = {}
        self._shutdown_lock = asyncio.Lock()
        self._pending_sweeper_task: asyncio.Task[None] | None = None
        self._leader_renew_task: asyncio.Task[None] | None = None
        self._zombie_sweeper_task: asyncio.Task[None] | None = None
        self._metrics_publisher_task: asyncio.Task[None] | None = None
        self._deferred_dispatcher_task: asyncio.Task[None] | None = None
        self._pending_catchup_task: asyncio.Task[None] | None = None
        self._leader_lease = secrets.token_urlsafe(24)
        self._leader_acquired = False
        self._started = False
        self._shutdown_complete = False
        self._update_processing_failures = 0
        self._dead_lettered_updates = 0
        self._recovery_failures = 0
        self._inflight_updates = 0
        self._capacity_available = asyncio.Event()
        self._capacity_available.set()
        self._deferred_by_bot: dict[int, deque[str | bytes]] = {}
        self._deferred_message_ids: set[str] = set()
        self._inflight_message_ids: set[str] = set()
        self._deferred_available = asyncio.Event()
        self._deferred_capacity_available = asyncio.Event()
        self._deferred_capacity_available.set()
        self._stream_fetch_lock = asyncio.Lock()
        self._pending_recovery_lock = asyncio.Lock()
        self._pending_recovery_cursor: str | bytes = "0-0"
        self._pending_catchup_complete = asyncio.Event()

    async def start(self) -> None:
        if self._started:
            return
        await self._acquire_leader()
        self._leader_renew_task = asyncio.create_task(
            self._renew_leader_loop(),
            name="private-qqcc-leader-renewal",
        )
        try:
            await self.ensure_consumer_group()
        except BaseException:
            self._leader_renew_task.cancel()
            await asyncio.gather(self._leader_renew_task, return_exceptions=True)
            self._leader_renew_task = None
            await self._release_leader()
            raise
        self._started = True
        await self.dependencies.recover_tasks(self.resolve_recovery_application)
        if self._stop_event.is_set():
            raise RuntimeError("Private QQCC Bot worker lease was lost during startup")
        try:
            await self.recover_pending()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Private QQCC initial pending recovery failed; continuous recovery "
                "will retry error_type=%s",
                type(exc).__name__,
            )
        self._pending_sweeper_task = asyncio.create_task(
            self._run_pending_sweeper(),
            name="private-qqcc-pending-sweeper",
        )
        self._zombie_sweeper_task = asyncio.create_task(
            self._run_zombie_sweeper(),
            name="private-qqcc-zombie-sweeper",
        )
        self._metrics_publisher_task = asyncio.create_task(
            self._run_metrics_publisher(),
            name="private-qqcc-metrics-publisher",
        )
        self._deferred_dispatcher_task = asyncio.create_task(
            self._run_deferred_dispatcher(),
            name="private-qqcc-deferred-dispatcher",
        )
        self._pending_catchup_task = asyncio.create_task(
            self._run_pending_catchup(),
            name="private-qqcc-pending-catchup",
        )

    async def run(self) -> None:
        try:
            await self.start()
            logger.info(
                "Private QQCC Bot worker started consumer=%s group=%s",
                self.consumer_name,
                self.consumer_group,
            )
            while not self._stop_event.is_set():
                try:
                    while not self._pending_catchup_complete.is_set():
                        try:
                            await asyncio.wait_for(
                                self._pending_catchup_complete.wait(),
                                timeout=1.0,
                            )
                        except asyncio.TimeoutError:
                            if self._stop_event.is_set():
                                return
                    await self._capacity_available.wait()
                    await self._deferred_capacity_available.wait()
                    remaining_capacity = max(
                        1,
                        self.max_inflight_updates - self._inflight_updates,
                    )
                    deferred_capacity = max(
                        1,
                        self.max_deferred_updates
                        - len(self._deferred_message_ids),
                    )
                    async with self._stream_fetch_lock:
                        streams = await self.dependencies.redis.xreadgroup(
                            groupname=self.consumer_group,
                            consumername=self.consumer_name,
                            streams={self.stream_key: ">"},
                            count=min(
                                self.batch_size,
                                remaining_capacity,
                                deferred_capacity,
                            ),
                            block=self.block_ms,
                        )
                        await self._dispatch_streams(streams)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Private QQCC Redis read failed error_type=%s",
                        type(exc).__name__,
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=self.retry_seconds
                        )
                    except asyncio.TimeoutError:
                        pass
        finally:
            await self.shutdown()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def _acquire_leader(self) -> None:
        acquired = await self.dependencies.redis.set(
            self.leader_key,
            self._leader_lease,
            ex=WORKER_LEADER_TTL_SECONDS,
            nx=True,
        )
        if not acquired:
            raise RuntimeError(
                "Another private QQCC Bot worker already owns the singleton lease"
            )
        self._leader_acquired = True

    async def _renew_leader_loop(self) -> None:
        while not self._leader_stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._leader_stop_event.wait(),
                    timeout=WORKER_LEADER_RENEW_SECONDS,
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                renewed = await self.dependencies.redis.eval(
                    _RENEW_LEADER_SCRIPT,
                    1,
                    self.leader_key,
                    self._leader_lease,
                    str(WORKER_LEADER_TTL_SECONDS),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._recovery_failures += 1
                logger.error(
                    "Private QQCC Bot worker singleton lease renewal failed "
                    "error_type=%s",
                    type(exc).__name__,
                )
                self.request_stop()
                return
            if int(renewed or 0) != 1:
                logger.error("Private QQCC Bot worker singleton lease was lost")
                self.request_stop()
                return

    async def _release_leader(self) -> None:
        if not self._leader_acquired:
            return
        try:
            await self.dependencies.redis.eval(
                _RELEASE_LEADER_SCRIPT,
                1,
                self.leader_key,
                self._leader_lease,
            )
        finally:
            self._leader_acquired = False

    async def ensure_consumer_group(self) -> None:
        try:
            await self.dependencies.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc).upper():
                raise
        except Exception as exc:
            if "BUSYGROUP" not in str(exc).upper():
                raise

    async def recover_pending(self) -> None:
        async with self._pending_recovery_lock:
            cursor: str | bytes = (
                "0-0"
                if self._pending_catchup_complete.is_set()
                else self._pending_recovery_cursor
            )
            while not self._stop_event.is_set():
                if self._inflight_updates >= self.max_inflight_updates:
                    self._capacity_available.clear()
                    self._pending_recovery_cursor = cursor
                    return
                if len(self._deferred_message_ids) >= self.max_deferred_updates:
                    self._deferred_capacity_available.clear()
                    self._pending_recovery_cursor = cursor
                    return
                try:
                    async with self._stream_fetch_lock:
                        result = await self.dependencies.redis.xautoclaim(
                            name=self.stream_key,
                            groupname=self.consumer_group,
                            consumername=self.consumer_name,
                            # While the singleton leader is starting, claim the
                            # entire old PEL regardless of idle age so a recent
                            # predecessor entry cannot be overtaken by a new
                            # ``>`` read. Periodic sweeps retain the normal idle
                            # threshold once the startup barrier is complete.
                            min_idle_time=(
                                self.pending_idle_ms
                                if self._pending_catchup_complete.is_set()
                                else 0
                            ),
                            start_id=cursor,
                            count=min(
                                self.batch_size,
                                self.max_inflight_updates - self._inflight_updates,
                                self.max_deferred_updates
                                - len(self._deferred_message_ids),
                            ),
                        )
                        if not isinstance(result, (list, tuple)) or len(result) < 2:
                            logger.error(
                                "Private QQCC pending recovery returned an invalid response"
                            )
                            self._pending_recovery_cursor = cursor
                            return
                        next_cursor, messages = result[0], result[1]
                        await self._dispatch_messages(messages)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._recovery_failures += 1
                    logger.error(
                        "Private QQCC pending recovery failed error_type=%s",
                        type(exc).__name__,
                    )
                    self._pending_recovery_cursor = cursor
                    return

                if _as_text(next_cursor) == "0-0":
                    self._pending_recovery_cursor = "0-0"
                    self._pending_catchup_complete.set()
                    return
                if _as_text(next_cursor) == _as_text(cursor) and not messages:
                    logger.error("Private QQCC pending recovery cursor did not advance")
                    self._pending_recovery_cursor = cursor
                    return
                cursor = next_cursor
                self._pending_recovery_cursor = cursor

    async def _run_metrics_publisher(self) -> None:
        while not self._stop_event.is_set():
            try:
                await publish_private_qqcc_worker_metrics(
                    self.dependencies.redis,
                    active_applications=len(self._applications),
                    update_processing_failures=self._update_processing_failures,
                    dead_lettered_updates=self._dead_lettered_updates,
                    recovery_failures=self._recovery_failures,
                    inflight_updates=self._inflight_updates,
                    max_inflight_updates=self.max_inflight_updates,
                    deferred_updates=len(self._deferred_message_ids),
                    redis_prefix=self.redis_prefix,
                    now=self.dependencies.now(),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Private QQCC metrics publish failed error_type=%s",
                    type(exc).__name__,
                )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.metrics_publish_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass

    async def _run_pending_catchup(self) -> None:
        while (
            not self._stop_event.is_set()
            and not self._pending_catchup_complete.is_set()
        ):
            await self._capacity_available.wait()
            await self._deferred_capacity_available.wait()
            await self.recover_pending()
            if self._pending_catchup_complete.is_set():
                return
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=0.1,
                )
                return
            except asyncio.TimeoutError:
                pass

    async def _run_pending_sweeper(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.pending_sweep_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass
            await self.recover_pending()
            try:
                await self.dependencies.recover_tasks(
                    self.resolve_recovery_application
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._recovery_failures += 1
                logger.error(
                    "Private QQCC periodic task recovery failed error_type=%s",
                    type(exc).__name__,
                )
            await self._evict_idle_applications()

    async def _run_zombie_sweeper(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.zombie_sweep_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                await self.dependencies.clean_zombies(
                    self.resolve_recovery_application
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._recovery_failures += 1
                logger.error(
                    "Private QQCC zombie cleanup failed error_type=%s",
                    type(exc).__name__,
                )

    async def _evict_idle_applications(self) -> None:
        cutoff = self.dependencies.monotonic() - self.application_idle_seconds
        for private_bot_id, managed in list(self._applications.items()):
            if private_bot_id in self._bot_queues:
                continue
            if managed.last_used_at > cutoff:
                continue
            bg_tasks = managed.application.bot_data.get("bg_tasks", set())
            if any(not task.done() for task in bg_tasks):
                continue
            await self._discard_application(private_bot_id)

    async def dispatch_message(
        self,
        message_id: str | bytes,
        fields: Mapping[str | bytes, Any],
        *,
        defer_on_backpressure: bool = False,
        deferred_resume: bool = False,
    ) -> bool:
        try:
            normalized = {_as_text(key): _as_text(value) for key, value in fields.items()}
            private_bot_id = int(normalized["private_bot_id"])
            update_id = int(normalized["update_id"])
            update_json = normalized["update_json"]
            received_at = datetime.fromtimestamp(
                float(normalized.get("received_at") or self.dependencies.now().timestamp())
            )
            if private_bot_id <= 0 or update_id < 0 or not update_json:
                raise ValueError("invalid stream fields")
        except (KeyError, TypeError, ValueError, UnicodeError):
            logger.error(
                "Dropping malformed private QQCC stream entry message_id=%s",
                _as_text(message_id),
            )
            await self._ack(message_id)
            return False

        entry = WebhookStreamEntry(
            message_id=message_id,
            private_bot_id=private_bot_id,
            update_id=update_id,
            update_json=update_json,
            received_at=received_at,
        )
        message_key = _as_text(message_id)
        if message_key in self._inflight_message_ids:
            return True
        if not deferred_resume and private_bot_id in self._deferred_by_bot:
            if defer_on_backpressure:
                self._defer_stream_message(
                    message_id=message_id,
                    private_bot_id=private_bot_id,
                )
            return False
        if self._inflight_updates >= self.max_inflight_updates:
            self._capacity_available.clear()
            if defer_on_backpressure:
                self._defer_stream_message(
                    message_id=message_id,
                    private_bot_id=private_bot_id,
                )
            return False
        queue = self._bot_queues.get(private_bot_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=self.per_bot_prefetch)
            self._bot_queues[private_bot_id] = queue
        if queue.full():
            if defer_on_backpressure:
                self._defer_stream_message(
                    message_id=message_id,
                    private_bot_id=private_bot_id,
                )
            return False
        task = self._bot_tasks.get(private_bot_id)
        if task is None or task.done():
            task = asyncio.create_task(
                self._consume_bot_queue(private_bot_id, queue),
                name=f"private-qqcc-bot-{private_bot_id}",
            )
            self._bot_tasks[private_bot_id] = task
        self._inflight_updates += 1
        self._inflight_message_ids.add(message_key)
        if self._inflight_updates >= self.max_inflight_updates:
            self._capacity_available.clear()
        queue.put_nowait(entry)
        return True

    async def wait_until_idle(self) -> None:
        queues = list(self._bot_queues.values())
        if queues:
            await asyncio.gather(*(queue.join() for queue in queues))

    async def resolve_active_application(
        self, private_bot_id: int
    ) -> TelegramApplication | None:
        record = await self.dependencies.store.get_runtime_record(private_bot_id)
        if record is None or not record.is_active:
            await self._discard_application(private_bot_id)
            return None
        try:
            return await self._get_or_create_application(record)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Private QQCC Application is unavailable private_bot_id=%s "
                "error_type=%s",
                private_bot_id,
                type(exc).__name__,
            )
            await self._mark_runtime_error_safe(
                private_bot_id,
                error_code="application_unavailable",
                disable_runtime=True,
            )
            return None

    async def resolve_recovery_application(
        self, private_bot_id: int
    ) -> TelegramApplication | None:
        """Resolve a delivery-only Application for already charged tasks.

        Owner/admin disablement rejects new webhook updates, but must not prevent
        an already accepted task from delivering its terminal result.
        """
        if self._stop_event.is_set():
            return None
        record = await self.dependencies.store.get_runtime_record(private_bot_id)
        if record is None:
            return None
        try:
            return await self._get_or_create_application(record)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Private QQCC recovery Application is unavailable private_bot_id=%s "
                "error_type=%s",
                private_bot_id,
                type(exc).__name__,
            )
            await self._mark_runtime_error_safe(
                private_bot_id,
                error_code="recovery_application_unavailable",
                disable_runtime=True,
            )
            return None

    async def shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._shutdown_complete:
                return
            self._stop_event.set()

            tasks = list(self._bot_tasks.values())
            if self._pending_sweeper_task is not None:
                self._pending_sweeper_task.cancel()
                tasks.append(self._pending_sweeper_task)
                self._pending_sweeper_task = None
            if self._zombie_sweeper_task is not None:
                self._zombie_sweeper_task.cancel()
                tasks.append(self._zombie_sweeper_task)
                self._zombie_sweeper_task = None
            if self._metrics_publisher_task is not None:
                self._metrics_publisher_task.cancel()
                tasks.append(self._metrics_publisher_task)
                self._metrics_publisher_task = None
            if self._deferred_dispatcher_task is not None:
                self._deferred_dispatcher_task.cancel()
                tasks.append(self._deferred_dispatcher_task)
                self._deferred_dispatcher_task = None
            if self._pending_catchup_task is not None:
                self._pending_catchup_task.cancel()
                tasks.append(self._pending_catchup_task)
                self._pending_catchup_task = None
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._bot_tasks.clear()
            self._bot_queues.clear()

            managed_apps = list(self._applications.values())
            self._applications.clear()
            for managed in managed_apps:
                await self._cancel_application_backgrounds(managed.application)
                await self._stop_application(managed.application)

            if self.dependencies.channel_membership_checker_shutdown is not None:
                try:
                    await self.dependencies.channel_membership_checker_shutdown()
                except Exception as exc:
                    logger.error(
                        "Official QQCC membership transport shutdown failed "
                        "error_type=%s",
                        type(exc).__name__,
                    )

            self._application_locks.clear()
            if self._leader_renew_task is not None:
                self._leader_stop_event.set()
                self._leader_renew_task.cancel()
                await asyncio.gather(
                    self._leader_renew_task,
                    return_exceptions=True,
                )
                self._leader_renew_task = None
            await self._release_leader()
            self._shutdown_complete = True
            logger.info("Private QQCC Bot worker stopped")

    async def _dispatch_streams(self, streams: Any) -> None:
        if not streams:
            return
        for stream in streams:
            if not isinstance(stream, (list, tuple)) or len(stream) != 2:
                continue
            await self._dispatch_messages(stream[1])

    async def _dispatch_messages(self, messages: Any) -> None:
        for message in messages or ():
            if not isinstance(message, (list, tuple)) or len(message) != 2:
                continue
            await self.dispatch_message(
                message[0],
                message[1],
                defer_on_backpressure=True,
            )

    def _defer_stream_message(
        self,
        *,
        message_id: str | bytes,
        private_bot_id: int,
    ) -> None:
        message_key = _as_text(message_id)
        if (
            message_key in self._deferred_message_ids
            or message_key in self._inflight_message_ids
        ):
            return
        if len(self._deferred_message_ids) >= self.max_deferred_updates:
            self._deferred_capacity_available.clear()
            logger.error(
                "Private QQCC deferred update id capacity exhausted; "
                "leaving entry in the Redis pending list"
            )
            return
        queue = self._deferred_by_bot.setdefault(private_bot_id, deque())
        queue.append(message_id)
        self._deferred_message_ids.add(message_key)
        self._deferred_available.set()
        if len(self._deferred_message_ids) >= self.max_deferred_updates:
            self._deferred_capacity_available.clear()

    def _pop_deferred_stream_message(
        self,
        *,
        private_bot_id: int,
        message_id: str | bytes,
    ) -> None:
        queue = self._deferred_by_bot.get(private_bot_id)
        if queue is None or not queue:
            return
        if _as_text(queue[0]) != _as_text(message_id):
            return
        queue.popleft()
        self._deferred_message_ids.discard(_as_text(message_id))
        if not queue:
            self._deferred_by_bot.pop(private_bot_id, None)
        if len(self._deferred_message_ids) < self.max_deferred_updates:
            self._deferred_capacity_available.set()
        if not self._deferred_message_ids:
            self._deferred_available.clear()

    async def _run_deferred_dispatcher(self) -> None:
        while not self._stop_event.is_set():
            await self._deferred_available.wait()
            if self._stop_event.is_set():
                return
            made_progress = False
            for private_bot_id in list(self._deferred_by_bot):
                if self._inflight_updates >= self.max_inflight_updates:
                    self._capacity_available.clear()
                    break
                deferred_queue = self._deferred_by_bot.get(private_bot_id)
                if not deferred_queue:
                    continue
                message_id = deferred_queue[0]
                try:
                    rows = await self.dependencies.redis.xrange(
                        name=self.stream_key,
                        min=message_id,
                        max=message_id,
                        count=1,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "Private QQCC deferred entry lookup failed message_id=%s "
                        "error_type=%s",
                        _as_text(message_id),
                        type(exc).__name__,
                    )
                    continue
                if not rows:
                    self._pop_deferred_stream_message(
                        private_bot_id=private_bot_id,
                        message_id=message_id,
                    )
                    made_progress = True
                    continue
                row_message_id, fields = rows[0]
                accepted = await self.dispatch_message(
                    row_message_id,
                    fields,
                    deferred_resume=True,
                )
                if accepted:
                    self._pop_deferred_stream_message(
                        private_bot_id=private_bot_id,
                        message_id=message_id,
                    )
                    made_progress = True
            if not made_progress:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=0.05,
                    )
                    return
                except asyncio.TimeoutError:
                    pass

    async def _consume_bot_queue(
        self,
        private_bot_id: int,
        queue: asyncio.Queue[WebhookStreamEntry],
    ) -> None:
        while True:
            try:
                entry = await asyncio.wait_for(
                    queue.get(),
                    timeout=self.application_idle_seconds,
                )
            except asyncio.TimeoutError:
                if not queue.empty():
                    continue
                managed = self._applications.get(private_bot_id)
                bg_tasks = (
                    getattr(managed.application, "bot_data", {}).get("bg_tasks", set())
                    if managed is not None
                    else set()
                )
                has_background = any(not task.done() for task in bg_tasks)
                if has_background:
                    continue
                if not queue.empty():
                    continue
                await self._discard_application(private_bot_id)
                if not queue.empty():
                    continue
                if self._bot_queues.get(private_bot_id) is queue:
                    self._bot_queues.pop(private_bot_id, None)
                if self._bot_tasks.get(private_bot_id) is asyncio.current_task():
                    self._bot_tasks.pop(private_bot_id, None)
                return
            try:
                while not self._stop_event.is_set():
                    try:
                        async with self._semaphore:
                            processed = await self._process_entry(entry)
                        if processed:
                            await self._ack(entry.message_id)
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self._update_processing_failures += 1
                        logger.error(
                            "Private QQCC update processing failed private_bot_id=%s "
                            "update_id=%s message_id=%s error_type=%s",
                            private_bot_id,
                            entry.update_id,
                            _as_text(entry.message_id),
                            type(exc).__name__,
                        )
                        try:
                            attempts = await self._record_update_failure(entry)
                        except Exception as failure_exc:
                            logger.error(
                                "Private QQCC update failure counter is unavailable "
                                "private_bot_id=%s update_id=%s error_type=%s",
                                private_bot_id,
                                entry.update_id,
                                type(failure_exc).__name__,
                            )
                        else:
                            if attempts >= MAX_UPDATE_PROCESSING_ATTEMPTS:
                                self._dead_lettered_updates += 1
                                await self._mark_runtime_error_safe(
                                    private_bot_id,
                                    error_code="update_dead_lettered",
                                    disable_runtime=False,
                                )
                                await self.dependencies.redis.set(
                                    self._processed_update_key(entry),
                                    "dead-letter",
                                    ex=PROCESSED_UPDATE_TTL_SECONDS,
                                )
                                await self._ack(entry.message_id)
                                logger.warning(
                                    "Private QQCC update moved to metadata-only dead letter "
                                    "private_bot_id=%s update_id=%s attempts=%s",
                                    private_bot_id,
                                    entry.update_id,
                                    attempts,
                                )
                                break
                        try:
                            await asyncio.wait_for(
                                self._stop_event.wait(),
                                timeout=self.retry_seconds,
                            )
                        except asyncio.TimeoutError:
                            pass
            finally:
                queue.task_done()
                self._inflight_message_ids.discard(_as_text(entry.message_id))
                self._inflight_updates = max(0, self._inflight_updates - 1)
                if self._inflight_updates < self.max_inflight_updates:
                    self._capacity_available.set()

    async def _process_entry(self, entry: WebhookStreamEntry) -> bool:
        processed_key = self._processed_update_key(entry)
        if await self.dependencies.redis.exists(processed_key):
            return True
        record = await self.dependencies.store.get_runtime_record(entry.private_bot_id)
        if record is None:
            await self._discard_application(entry.private_bot_id)
            return True
        if not record.is_active:
            await self._discard_application(entry.private_bot_id)
            return True

        try:
            application = await self._get_or_create_application(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._mark_runtime_error_safe(
                entry.private_bot_id,
                error_code="application_unavailable",
                disable_runtime=True,
            )
            return True
        try:
            payload = json.loads(entry.update_json)
            if not isinstance(payload, dict):
                raise ValueError("Telegram update must be an object")
            update_obj = self.dependencies.update_decoder(payload, application.bot)
            admission = PrivateBotUpdateAdmissionScope(
                private_bot_id=entry.private_bot_id,
                update_id=entry.update_id,
            )
            with activate_private_bot_update_scope(admission):
                await application.process_update(update_obj)
            await admission.wait_until_durable(
                timeout_seconds=self.admission_timeout_seconds
            )
            if admission.failed:
                raise RuntimeError("private QQCC update handler failed")
            marked = await self.dependencies.redis.set(
                processed_key,
                "1",
                ex=PROCESSED_UPDATE_TTL_SECONDS,
                nx=True,
            )
            if not marked and not await self.dependencies.redis.exists(processed_key):
                raise RuntimeError("private QQCC update marker is unavailable")
            await self.dependencies.store.mark_update_processed(
                entry.private_bot_id,
                webhook_received_at=entry.received_at,
                processed_at=self.dependencies.now(),
            )
        finally:
            payload = None
        return True

    def _processed_update_key(self, entry: WebhookStreamEntry) -> str:
        return f"{self.stream_key}:processed:{entry.private_bot_id}:{entry.update_id}"

    async def _record_update_failure(self, entry: WebhookStreamEntry) -> int:
        key = (
            f"{self.stream_key}:failures:{entry.private_bot_id}:{entry.update_id}"
        )
        attempts = await self.dependencies.redis.eval(
            _INCREMENT_FAILURE_SCRIPT,
            1,
            key,
            str(FAILED_UPDATE_TTL_SECONDS),
        )
        return int(attempts)

    async def _get_or_create_application(
        self, record: PrivateBotRuntimeRecord
    ) -> TelegramApplication:
        private_bot_id = record.private_bot_id
        lock = self._application_locks.setdefault(private_bot_id, asyncio.Lock())
        async with lock:
            existing = self._applications.get(private_bot_id)
            if (
                existing is not None
                and existing.token_fingerprint == record.token_fingerprint
            ):
                existing.last_used_at = self.dependencies.monotonic()
                return existing.application
            if existing is not None:
                self._applications.pop(private_bot_id, None)
                await self._cancel_application_backgrounds(existing.application)
                await self._stop_application(existing.application)

            token = self.dependencies.credential_cipher.decrypt(
                record.token_ciphertext,
                key_version=record.token_key_version,
                associated_data=record.webhook_public_id,
            )

            async def load_config() -> dict[str, Any]:
                raw_config = await self.dependencies.store.load_config(private_bot_id)
                return self.dependencies.normalize_config(raw_config)

            application = self.dependencies.application_builder(
                token,
                bot_client_type=build_private_bot_client_type(private_bot_id),
                private_bot_id=private_bot_id,
                config_loader=load_config,
                include_private_bot_provisioning=False,
                recover_tasks=False,
                close_shared_redis_on_shutdown=False,
                telegram_base_url=build_private_telegram_bot_base_url(),
                telegram_file_base_url=resolve_private_telegram_file_base_url(),
                setup_bot_commands=False,
                request_connection_pool_size=4,
                channel_membership_checker=(
                    self.dependencies.channel_membership_checker
                ),
            )
            token = ""
            initialized = False
            post_initialized = False
            try:
                await application.initialize()
                initialized = True
                post_init = getattr(application, "post_init", None)
                if post_init is not None:
                    await post_init(application)
                    post_initialized = True
                await application.start()
            except BaseException:
                if initialized:
                    try:
                        await application.shutdown()
                    except Exception:
                        pass
                if post_initialized:
                    post_shutdown = getattr(application, "post_shutdown", None)
                    if post_shutdown is not None:
                        try:
                            await post_shutdown(application)
                        except Exception:
                            pass
                raise
            self._applications[private_bot_id] = _ManagedApplication(
                application=application,
                token_fingerprint=record.token_fingerprint,
                last_used_at=self.dependencies.monotonic(),
            )
            return application

    async def _mark_runtime_error_safe(
        self,
        private_bot_id: int,
        *,
        error_code: str,
        disable_runtime: bool,
    ) -> None:
        try:
            await self.dependencies.store.mark_runtime_error(
                private_bot_id,
                error_code=error_code,
                occurred_at=self.dependencies.now(),
                disable_runtime=disable_runtime,
            )
        except Exception as exc:
            logger.error(
                "Private QQCC runtime error persistence failed "
                "private_bot_id=%s error_type=%s",
                private_bot_id,
                type(exc).__name__,
            )

    async def _discard_application(self, private_bot_id: int) -> None:
        lock = self._application_locks.setdefault(private_bot_id, asyncio.Lock())
        async with lock:
            managed = self._applications.get(private_bot_id)
            if managed is None:
                return
            # Pausing or disabling a tenant only rejects new work. Paid task
            # monitors and continuation deliveries already attached to this
            # Application must keep a live Telegram transport until they
            # finish; idle eviction will reclaim it afterwards.
            bg_tasks = managed.application.bot_data.get("bg_tasks", set())
            if any(not task.done() for task in bg_tasks):
                return
            self._applications.pop(private_bot_id, None)
            await self._stop_application(managed.application)

    async def _stop_application(self, application: TelegramApplication) -> None:
        try:
            await application.stop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to stop private QQCC Application error_type=%s",
                type(exc).__name__,
            )
        try:
            await application.shutdown()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to shut down private QQCC Application error_type=%s",
                type(exc).__name__,
            )
        post_shutdown = getattr(application, "post_shutdown", None)
        if post_shutdown is not None:
            try:
                await post_shutdown(application)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Private QQCC post-shutdown failed error_type=%s",
                    type(exc).__name__,
                )

    async def _cancel_application_backgrounds(
        self,
        application: TelegramApplication,
    ) -> None:
        tasks = [
            task
            for task in application.bot_data.get("bg_tasks", set())
            if task is not asyncio.current_task() and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ack(self, message_id: str | bytes) -> bool:
        try:
            acknowledged = await self.dependencies.redis.eval(
                _ACK_AND_DELETE_SCRIPT,
                1,
                self.stream_key,
                self.consumer_group,
                message_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Private QQCC stream ACK failed message_id=%s error_type=%s",
                _as_text(message_id),
                type(exc).__name__,
            )
            return False
        if int(acknowledged or 0) != 1:
            logger.warning(
                "Private QQCC stream entry was not ACKed message_id=%s",
                _as_text(message_id),
            )
            return False
        return True


def build_default_worker() -> PrivateQqccBotWorker:
    from src.database.core import AsyncSessionLocal
    from src.services.qqcc_channel_membership_service import (
        build_official_qqcc_channel_membership_checker,
    )
    from src.services.redis_client import redis_client

    channel_membership_checker = build_official_qqcc_channel_membership_checker(
        redis=redis_client.redis,
        redis_prefix=REDIS_PREFIX,
    )

    dependencies = PrivateQqccBotWorkerDependencies(
        redis=redis_client.redis,
        store=SqlAlchemyPrivateQqccBotStore(AsyncSessionLocal),
        credential_cipher=PrivateBotCredentialCipher.from_environment(),
        channel_membership_checker=channel_membership_checker,
        channel_membership_checker_shutdown=channel_membership_checker.close,
    )
    return PrivateQqccBotWorker(
        dependencies,
        redis_prefix=REDIS_PREFIX,
        consumer_group=os.getenv(
            "PRIVATE_QQCC_BOT_WORKER_CONSUMER_GROUP", DEFAULT_CONSUMER_GROUP
        ),
        consumer_name=os.getenv("PRIVATE_QQCC_BOT_WORKER_CONSUMER_NAME") or None,
        concurrency=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_CONCURRENCY", DEFAULT_CONCURRENCY
        ),
        batch_size=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE
        ),
        block_ms=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_BLOCK_MS", DEFAULT_BLOCK_MS
        ),
        pending_idle_ms=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_PENDING_IDLE_MS", DEFAULT_PENDING_IDLE_MS
        ),
        retry_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_WORKER_RETRY_SECONDS", DEFAULT_RETRY_SECONDS
        ),
        pending_sweep_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_WORKER_PENDING_SWEEP_SECONDS",
            DEFAULT_PENDING_SWEEP_SECONDS,
        ),
        application_idle_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_APPLICATION_IDLE_SECONDS",
            DEFAULT_APPLICATION_IDLE_SECONDS,
        ),
        admission_timeout_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_ADMISSION_TIMEOUT_SECONDS",
            DEFAULT_ADMISSION_TIMEOUT_SECONDS,
        ),
        zombie_sweep_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_ZOMBIE_SWEEP_SECONDS",
            DEFAULT_ZOMBIE_SWEEP_SECONDS,
        ),
        metrics_publish_seconds=_positive_float_from_env(
            "PRIVATE_QQCC_BOT_METRICS_PUBLISH_SECONDS",
            DEFAULT_METRICS_PUBLISH_SECONDS,
        ),
        max_inflight_updates=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_MAX_INFLIGHT_UPDATES",
            DEFAULT_MAX_INFLIGHT_UPDATES,
        ),
        per_bot_prefetch=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_PER_BOT_PREFETCH",
            DEFAULT_PER_BOT_PREFETCH,
        ),
        max_deferred_updates=_positive_int_from_env(
            "PRIVATE_QQCC_BOT_WORKER_MAX_DEFERRED_UPDATES",
            DEFAULT_MAX_DEFERRED_UPDATES,
        ),
    )


async def _run_default_worker() -> None:
    from src.services.redis_client import redis_client

    worker = build_default_worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await worker.run()
    finally:
        await redis_client.close()


def main() -> None:
    from src.logger import setup_logging

    setup_logging()
    if os.getenv("PRIVATE_QQCC_BOT_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        logger.error(
            "Private QQCC Bot worker refused to start because the rollout gate is disabled"
        )
        return
    try:
        asyncio.run(_run_default_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
