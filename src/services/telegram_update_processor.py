import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Hashable

from telegram import Update
from telegram.ext import BaseUpdateProcessor

logger = logging.getLogger("bot.update_processor")

DEFAULT_MAIN_BOT_MAX_CONCURRENT_UPDATES = 32
MAX_MAIN_BOT_MAX_CONCURRENT_UPDATES = 256
MIN_ADMITTED_UPDATES = 256
MAX_ADMITTED_UPDATES = 4096


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class PerUserUpdateProcessor(BaseUpdateProcessor):
    """Run updates concurrently while preserving strict ordering for each user."""

    def __init__(self, max_concurrent_updates: int) -> None:
        if max_concurrent_updates < 1:
            raise ValueError("max_concurrent_updates must be positive")
        admission_limit = min(
            MAX_ADMITTED_UPDATES,
            max(MIN_ADMITTED_UPDATES, max_concurrent_updates * 8),
        )
        # PTB acquires the BaseUpdateProcessor semaphore before invoking
        # do_process_update. Keep that admission window wider than the real
        # handler limit so one user's queued updates cannot occupy every slot.
        super().__init__(max_concurrent_updates=admission_limit)
        self._handler_semaphore = asyncio.BoundedSemaphore(max_concurrent_updates)
        self._entries: dict[Hashable, _LockEntry] = {}
        self._entries_guard = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    @staticmethod
    def _serialization_key(update: object) -> Hashable:
        if isinstance(update, Update):
            effective_user = update.effective_user
            effective_chat = update.effective_chat
        else:
            effective_user = getattr(update, "effective_user", None)
            effective_chat = getattr(update, "effective_chat", None)

        user_id = getattr(effective_user, "id", None)
        if user_id is not None:
            return ("user", user_id)

        chat_id = getattr(effective_chat, "id", None)
        if chat_id is not None:
            return ("chat", chat_id)

        # Updates without a user or chat are rare system-level events. Keeping
        # them serial is safer than allowing unknown shared state to race.
        return ("system", 0)

    async def _acquire_entry(self, key: Hashable) -> _LockEntry:
        async with self._entries_guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock())
                self._entries[key] = entry
            entry.users += 1
            return entry

    async def _release_entry(self, key: Hashable, entry: _LockEntry) -> None:
        async with self._entries_guard:
            entry.users -= 1
            if entry.users == 0 and self._entries.get(key) is entry:
                self._entries.pop(key, None)

    async def do_process_update(self, update: object, coroutine) -> None:
        key = self._serialization_key(update)
        entry = await self._acquire_entry(key)
        queued_at = time.perf_counter()
        update_id = getattr(update, "update_id", None)
        coroutine_started = False

        try:
            async with entry.lock:
                async with self._handler_semaphore:
                    started_at = time.perf_counter()
                    queue_wait_ms = (started_at - queued_at) * 1000
                    try:
                        coroutine_started = True
                        await coroutine
                    finally:
                        handler_duration_ms = (time.perf_counter() - started_at) * 1000
                        logger.info(
                            "telegram_update_timing update_id=%s key=%s "
                            "queue_wait_ms=%.1f handler_duration_ms=%.1f",
                            update_id,
                            key,
                            queue_wait_ms,
                            handler_duration_ms,
                        )
        finally:
            if not coroutine_started:
                close = getattr(coroutine, "close", None)
                if callable(close):
                    close()
            await self._release_entry(key, entry)


def build_main_bot_update_processor() -> PerUserUpdateProcessor:
    raw_limit = os.getenv(
        "MAIN_BOT_MAX_CONCURRENT_UPDATES",
        str(DEFAULT_MAIN_BOT_MAX_CONCURRENT_UPDATES),
    )
    try:
        limit = int(raw_limit)
    except ValueError:
        logger.warning(
            "Invalid MAIN_BOT_MAX_CONCURRENT_UPDATES=%r; using %s",
            raw_limit,
            DEFAULT_MAIN_BOT_MAX_CONCURRENT_UPDATES,
        )
        limit = DEFAULT_MAIN_BOT_MAX_CONCURRENT_UPDATES

    limit = max(1, min(limit, MAX_MAIN_BOT_MAX_CONCURRENT_UPDATES))
    return PerUserUpdateProcessor(max_concurrent_updates=limit)
