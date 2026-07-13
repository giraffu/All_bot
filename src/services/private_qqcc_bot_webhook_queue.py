import asyncio
import json
import logging
import time
from typing import Any

from config import REDIS_PREFIX
from src.services.redis_client import redis_client


logger = logging.getLogger(__name__)

PRIVATE_QQCC_BOT_WEBHOOK_DEDUPE_TTL_SECONDS = 86_400

_ENQUEUE_UPDATE_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 1 then
    redis.pcall("HINCRBY", KEYS[3], "webhook_duplicates_total", 1)
    if tonumber(ARGV[6]) > 0 then
        redis.pcall("HINCRBY", KEYS[3], "webhook_queue_errors_total", ARGV[6])
    end
    return 0
end

local stream_entry_id = redis.call("XADD",
    KEYS[2],
    "*",
    "private_bot_id", ARGV[2],
    "update_id", ARGV[3],
    "update_json", ARGV[4],
    "received_at", ARGV[5]
)

local set_result = redis.pcall("SET", KEYS[1], "1", "EX", ARGV[1])
if type(set_result) == "table" and set_result.err then
    redis.call("XDEL", KEYS[2], stream_entry_id)
    return redis.error_reply(set_result.err)
end

redis.pcall("HINCRBY", KEYS[3], "webhook_enqueued_total", 1)
if tonumber(ARGV[6]) > 0 then
    redis.pcall("HINCRBY", KEYS[3], "webhook_queue_errors_total", ARGV[6])
end
return 1
"""


class PrivateQqccBotWebhookQueueError(RuntimeError):
    """The webhook update could not be durably accepted by Redis."""


class PrivateQqccBotWebhookQueue:
    def __init__(
        self,
        *,
        redis=None,
        redis_prefix: str = REDIS_PREFIX,
        clock=time.time,
    ):
        self._redis = redis if redis is not None else redis_client.redis
        self._redis_prefix = redis_prefix
        self._clock = clock
        self._deferred_queue_errors = 0
        self._metrics_lock = asyncio.Lock()

    async def enqueue(
        self,
        *,
        private_bot_id: int,
        update_id: int,
        update: dict[str, Any],
    ) -> bool:
        dedupe_key = (
            f"{self._redis_prefix}private_qqcc_bot:webhook:dedupe:"
            f"{private_bot_id}:{update_id}"
        )
        stream_key = f"{self._redis_prefix}private_qqcc_bot:webhook:updates"
        metrics_key = f"{self._redis_prefix}private_qqcc_bot:metrics:counters"
        update_json = json.dumps(
            update,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        async with self._metrics_lock:
            deferred_queue_errors = self._deferred_queue_errors
            self._deferred_queue_errors = 0
        try:
            result = await self._redis.eval(
                _ENQUEUE_UPDATE_SCRIPT,
                3,
                dedupe_key,
                stream_key,
                metrics_key,
                str(PRIVATE_QQCC_BOT_WEBHOOK_DEDUPE_TTL_SECONDS),
                str(private_bot_id),
                str(update_id),
                update_json,
                str(self._clock()),
                str(deferred_queue_errors),
            )
            numeric_result = int(result)
            if numeric_result not in (0, 1):
                raise ValueError(f"Unexpected Redis enqueue result: {numeric_result}")
            return numeric_result == 1
        except asyncio.CancelledError:
            async with self._metrics_lock:
                self._deferred_queue_errors += deferred_queue_errors
            raise
        except Exception as exc:
            async with self._metrics_lock:
                self._deferred_queue_errors += deferred_queue_errors + 1
            logger.error(
                "Failed to enqueue private QQCC Bot webhook update "
                "for private_bot_id=%s update_id=%s",
                private_bot_id,
                update_id,
            )
            raise PrivateQqccBotWebhookQueueError(
                "Private QQCC Bot webhook queue is unavailable"
            ) from exc


_default_webhook_queue = PrivateQqccBotWebhookQueue()


async def enqueue_private_qqcc_bot_update(
    *,
    private_bot_id: int,
    update_id: int,
    update: dict[str, Any],
) -> bool:
    return await _default_webhook_queue.enqueue(
        private_bot_id=private_bot_id,
        update_id=update_id,
        update=update,
    )
