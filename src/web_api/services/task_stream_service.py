import asyncio
import json
import os
import time
from typing import Any, Awaitable, Callable

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sse_starlette.sse import EventSourceResponse
from src.core.task_status_mapper import is_backend_terminal_status

TASK_STREAM_STATUS_CACHE_TTL_SECONDS = float(
    os.getenv("TASK_STREAM_STATUS_CACHE_TTL_SECONDS", "2.0")
)
TASK_STREAM_STATUS_CACHE_MAX_ENTRIES = int(
    os.getenv("TASK_STREAM_STATUS_CACHE_MAX_ENTRIES", "5000")
)
TASK_STREAM_PENDING_STATUS_POLL_INITIAL_SECONDS = float(
    os.getenv("TASK_STREAM_PENDING_STATUS_POLL_INITIAL_SECONDS", "5.0")
)
TASK_STREAM_PENDING_STATUS_POLL_MAX_SECONDS = float(
    os.getenv("TASK_STREAM_PENDING_STATUS_POLL_MAX_SECONDS", "20.0")
)
TASK_STREAM_RUNNING_STATUS_POLL_INITIAL_SECONDS = float(
    os.getenv("TASK_STREAM_RUNNING_STATUS_POLL_INITIAL_SECONDS", "10.0")
)
TASK_STREAM_RUNNING_STATUS_POLL_MAX_SECONDS = float(
    os.getenv("TASK_STREAM_RUNNING_STATUS_POLL_MAX_SECONDS", "20.0")
)
TASK_STREAM_STATUS_POLL_BACKOFF_MULTIPLIER = float(
    os.getenv("TASK_STREAM_STATUS_POLL_BACKOFF_MULTIPLIER", "2.0")
)

_TASK_STREAM_POLL_SIGNATURE_FIELDS = (
    "status",
    "queue_pos",
    "progress",
    "progress_percent",
    "progress_percentage",
    "percentage",
    "current_step",
    "total_steps",
    "eta",
    "error_msg",
)
_TASK_STREAM_STATUS_FETCH_ERROR_SIGNATURE = ("fetch_error",)
_TASK_STREAM_PUBSUB_TRANSIENT_ERRORS = (
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)

_task_stream_status_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_task_stream_status_locks: dict[tuple[str, str], asyncio.Lock] = {}


def clear_task_stream_status_cache() -> None:
    _task_stream_status_cache.clear()
    _task_stream_status_locks.clear()


def _prune_task_stream_status_cache(now: float) -> None:
    if (
        TASK_STREAM_STATUS_CACHE_MAX_ENTRIES <= 0
        or len(_task_stream_status_cache) <= TASK_STREAM_STATUS_CACHE_MAX_ENTRIES
    ):
        return

    def remove_if_unlocked(cache_key: tuple[str, str]) -> bool:
        lock = _task_stream_status_locks.get(cache_key)
        if lock and lock.locked():
            return False
        _task_stream_status_cache.pop(cache_key, None)
        _task_stream_status_locks.pop(cache_key, None)
        return True

    for cache_key, (expires_at, _data) in list(_task_stream_status_cache.items()):
        if expires_at <= now:
            remove_if_unlocked(cache_key)

    overflow = len(_task_stream_status_cache) - TASK_STREAM_STATUS_CACHE_MAX_ENTRIES
    if overflow <= 0:
        return

    for cache_key, _cached in sorted(
        _task_stream_status_cache.items(),
        key=lambda item: item[1][0],
    ):
        if overflow <= 0:
            break
        if remove_if_unlocked(cache_key):
            overflow -= 1


def _task_stream_status_poll_initial_interval(is_running: bool) -> float:
    configured = (
        TASK_STREAM_RUNNING_STATUS_POLL_INITIAL_SECONDS
        if is_running
        else TASK_STREAM_PENDING_STATUS_POLL_INITIAL_SECONDS
    )
    return max(configured, 0.5)


def _task_stream_status_poll_max_interval(is_running: bool) -> float:
    initial_interval = _task_stream_status_poll_initial_interval(is_running)
    configured = (
        TASK_STREAM_RUNNING_STATUS_POLL_MAX_SECONDS
        if is_running
        else TASK_STREAM_PENDING_STATUS_POLL_MAX_SECONDS
    )
    return max(configured, initial_interval)


def _next_task_stream_status_poll_interval(
    *,
    current_interval: float,
    is_running: bool,
    status_changed: bool,
) -> float:
    initial_interval = _task_stream_status_poll_initial_interval(is_running)
    if status_changed:
        return initial_interval

    multiplier = max(TASK_STREAM_STATUS_POLL_BACKOFF_MULTIPLIER, 1.0)
    max_interval = _task_stream_status_poll_max_interval(is_running)
    return min(max_interval, max(current_interval, initial_interval) * multiplier)


def _build_task_stream_status_poll_signature(
    status_data: dict[str, Any],
) -> tuple[Any, ...]:
    if status_data.get("not_found"):
        return ("not_found",)
    return tuple(status_data.get(field) for field in _TASK_STREAM_POLL_SIGNATURE_FIELDS)


async def _fetch_task_status_full(
    *,
    task_id: str,
    api_base: str,
    httpx_async_client_factory,
    logger,
) -> dict[str, Any] | None:
    cache_key = (api_base, task_id)
    now = time.monotonic()
    cached = _task_stream_status_cache.get(cache_key)
    if (
        TASK_STREAM_STATUS_CACHE_TTL_SECONDS > 0
        and cached
        and cached[0] > now
    ):
        return dict(cached[1])

    lock = _task_stream_status_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _task_stream_status_cache.get(cache_key)
        if (
            TASK_STREAM_STATUS_CACHE_TTL_SECONDS > 0
            and cached
            and cached[0] > now
        ):
            return dict(cached[1])

        status_data = await _fetch_task_status_uncached(
            task_id=task_id,
            api_base=api_base,
            httpx_async_client_factory=httpx_async_client_factory,
            logger=logger,
        )
        if status_data is None:
            _task_stream_status_locks.pop(cache_key, None)
            return None
        if status_data is not None and TASK_STREAM_STATUS_CACHE_TTL_SECONDS > 0:
            now = time.monotonic()
            expires_at = now + TASK_STREAM_STATUS_CACHE_TTL_SECONDS
            _task_stream_status_cache[cache_key] = (
                expires_at,
                dict(status_data),
            )
            _prune_task_stream_status_cache(now)
        return status_data


async def _fetch_task_status_uncached(
    *,
    task_id: str,
    api_base: str,
    httpx_async_client_factory,
    logger,
) -> dict[str, Any] | None:
    try:
        async with httpx_async_client_factory() as client:
            resp = await client.get(f"{api_base}/status/{task_id}", timeout=2.0)
            if resp.status_code == 404:
                return {"not_found": True}
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code is not None:
            logger.error(
                "Unexpected status while getting task %s state: %s",
                task_id,
                status_code,
            )
        else:
            logger.error("Error getting status for %s: %s", task_id, exc)
    return None


def _build_connected_event(task_id: str) -> dict[str, str]:
    return {
        "event": "connected",
        "data": json.dumps({"status": "listening", "task_id": task_id}),
    }


def _build_progress_event(payload: dict[str, Any] | str) -> dict[str, str]:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return {"event": "progress", "data": data}


async def _build_not_found_event(
    *,
    task_id: str,
    user_id: int,
    session_factory,
    build_not_found_progress_payload: Callable[[str, int, Any], Awaitable[dict[str, Any]]],
) -> dict[str, str]:
    return _build_progress_event(
        await build_not_found_progress_payload(task_id, user_id, session_factory)
    )


def _build_terminal_event(
    *,
    status_data: dict[str, Any],
    task_id: str,
    build_terminal_progress_payload: Callable[[dict[str, Any], str], dict[str, Any] | None],
) -> dict[str, str] | None:
    terminal_payload = build_terminal_progress_payload(status_data, task_id)
    if terminal_payload is None:
        return None
    return _build_progress_event(terminal_payload)


def _resolve_status_transition(
    *,
    status_data: dict[str, Any],
    task_id: str,
    build_terminal_progress_payload: Callable[[dict[str, Any], str], dict[str, Any] | None],
) -> tuple[dict[str, str] | None, bool, bool]:
    status = status_data.get("status")
    if status == "running":
        return None, True, False

    terminal_event = _build_terminal_event(
        status_data=status_data,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event is not None:
        return terminal_event, False, True

    return None, False, is_backend_terminal_status(status)


def _extract_message_payload(message_data: Any) -> str:
    if isinstance(message_data, bytes):
        return message_data.decode("utf-8")
    return message_data


async def _subscribe_task_pubsub(*, redis, channel: str, task_id: str, logger):
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
    except Exception as exc:
        logger.warning(
            "Task stream Pub/Sub subscribe failed for task %s; using status polling: %s",
            task_id,
            exc,
        )
        pubsub = locals().get("pubsub")
        if pubsub is not None:
            await _close_task_pubsub(
                pubsub=pubsub,
                channel=channel,
                task_id=task_id,
                logger=logger,
            )
        return None


async def _close_task_pubsub(*, pubsub, channel: str, task_id: str, logger) -> None:
    try:
        await pubsub.unsubscribe(channel)
    except Exception as exc:
        logger.debug(
            "Task stream Pub/Sub unsubscribe failed for task %s: %s",
            task_id,
            exc,
        )
    try:
        await pubsub.close()
    except Exception as exc:
        logger.debug(
            "Task stream Pub/Sub close failed for task %s: %s",
            task_id,
            exc,
        )


async def _get_task_pubsub_message(
    *,
    pubsub,
    task_id: str,
    logger,
) -> tuple[Any, bool]:
    try:
        return (
            await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            ),
            True,
        )
    except _TASK_STREAM_PUBSUB_TRANSIENT_ERRORS as exc:
        logger.warning(
            "Task stream Pub/Sub disconnected for task %s; using status polling: %s",
            task_id,
            exc,
        )
        return None, False


async def _build_initial_stream_transition(
    *,
    runtime_task_id_val: str,
    task_id: str,
    user_id: int,
    session_factory,
    api_base: str,
    httpx_async_client_factory,
    logger,
    build_not_found_progress_payload,
    build_terminal_progress_payload,
    history_terminal: bool = False,
) -> tuple[list[dict[str, str]], bool, bool, tuple[Any, ...] | None]:
    events: list[dict[str, str]] = []
    if history_terminal:
        events.append(
            await _build_not_found_event(
                task_id=task_id,
                user_id=user_id,
                session_factory=session_factory,
                build_not_found_progress_payload=build_not_found_progress_payload,
            )
        )
        return events, False, True, None

    initial_status = await _fetch_task_status_full(
        task_id=runtime_task_id_val,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
    )
    if not initial_status:
        return events, False, False, _TASK_STREAM_STATUS_FETCH_ERROR_SIGNATURE
    status_signature = _build_task_stream_status_poll_signature(initial_status)
    if initial_status.get("not_found"):
        events.append(
            await _build_not_found_event(
                task_id=task_id,
                user_id=user_id,
                session_factory=session_factory,
                build_not_found_progress_payload=build_not_found_progress_payload,
            )
        )
        return events, False, True, status_signature

    terminal_event, became_running, should_stop = _resolve_status_transition(
        status_data=initial_status,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event:
        events.append(terminal_event)
    return events, became_running, should_stop, status_signature


async def _build_pubsub_stream_transition(
    *,
    message,
    task_id: str,
    build_terminal_progress_payload,
) -> tuple[dict[str, str] | None, bool, bool]:
    if not message:
        return None, False, False

    data = _extract_message_payload(message["data"])
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return _build_progress_event(data), False, False

    terminal_event, became_running, should_stop = _resolve_status_transition(
        status_data=parsed,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event:
        return terminal_event, became_running, should_stop
    return _build_progress_event(parsed), became_running, should_stop


async def _build_queue_poll_transition(
    *,
    runtime_task_id_val: str,
    task_id: str,
    user_id: int,
    session_factory,
    api_base: str,
    httpx_async_client_factory,
    logger,
    build_not_found_progress_payload,
    build_terminal_progress_payload,
) -> tuple[list[dict[str, str]], bool, bool, tuple[Any, ...] | None]:
    events: list[dict[str, str]] = []
    status_data = await _fetch_task_status_full(
        task_id=runtime_task_id_val,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
    )
    if not status_data:
        return events, False, False, _TASK_STREAM_STATUS_FETCH_ERROR_SIGNATURE
    status_signature = _build_task_stream_status_poll_signature(status_data)
    if status_data.get("not_found"):
        events.append(
            await _build_not_found_event(
                task_id=task_id,
                user_id=user_id,
                session_factory=session_factory,
                build_not_found_progress_payload=build_not_found_progress_payload,
            )
        )
        return events, False, True, status_signature

    terminal_event, became_running, should_stop = _resolve_status_transition(
        status_data=status_data,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event:
        events.append(terminal_event)
        return events, became_running, True, status_signature
    if should_stop:
        return events, became_running, True, status_signature

    queue_pos = status_data.get("queue_pos")
    if queue_pos is not None:
        events.append(
            _build_progress_event({"status": "pending", "queue_pos": queue_pos})
        )
    return events, became_running, False, status_signature


def build_task_status_stream_response(
    *,
    task_id: str,
    runtime_task_id: str | None,
    user_id: int,
    session_factory,
    redis,
    api_base: str,
    httpx_async_client_factory,
    logger,
    build_not_found_progress_payload: Callable[[str, int, Any], Awaitable[dict[str, Any]]],
    build_terminal_progress_payload: Callable[[dict[str, Any], str], dict[str, Any] | None],
    history_terminal: bool = False,
) -> EventSourceResponse:
    async def event_generator():
        runtime_task_id_val = runtime_task_id or task_id
        channel = f"comfy:task_events:{runtime_task_id_val}"
        pubsub = await _subscribe_task_pubsub(
            redis=redis,
            channel=channel,
            task_id=runtime_task_id_val,
            logger=logger,
        )

        try:
            yield _build_connected_event(task_id)
            is_running = False
            initial_events, became_running, should_stop, last_status_signature = (
                await _build_initial_stream_transition(
                    runtime_task_id_val=runtime_task_id_val,
                    task_id=task_id,
                    user_id=user_id,
                    session_factory=session_factory,
                    api_base=api_base,
                    httpx_async_client_factory=httpx_async_client_factory,
                    logger=logger,
                    build_not_found_progress_payload=build_not_found_progress_payload,
                    build_terminal_progress_payload=build_terminal_progress_payload,
                    history_terminal=history_terminal,
                )
            )
            for event in initial_events:
                yield event
            if became_running:
                is_running = True
            if should_stop:
                return

            status_check_interval = _task_stream_status_poll_initial_interval(is_running)
            last_status_check = (
                asyncio.get_event_loop().time() - status_check_interval - 0.001
            )

            while True:
                message = None
                if pubsub is not None:
                    message, pubsub_active = await _get_task_pubsub_message(
                        pubsub=pubsub,
                        task_id=runtime_task_id_val,
                        logger=logger,
                    )
                    if not pubsub_active:
                        await _close_task_pubsub(
                            pubsub=pubsub,
                            channel=channel,
                            task_id=runtime_task_id_val,
                            logger=logger,
                        )
                        pubsub = None
                pubsub_event, became_running, should_stop = (
                    await _build_pubsub_stream_transition(
                        message=message,
                        task_id=task_id,
                        build_terminal_progress_payload=build_terminal_progress_payload,
                    )
                )
                if pubsub_event:
                    yield pubsub_event
                if became_running:
                    is_running = True
                    status_check_interval = _task_stream_status_poll_initial_interval(
                        is_running
                    )
                if should_stop:
                    break

                current_time = asyncio.get_event_loop().time()
                if pubsub_event:
                    last_status_check = current_time
                if current_time - last_status_check > status_check_interval:
                    (
                        queue_events,
                        became_running,
                        should_stop,
                        status_signature,
                    ) = (
                        await _build_queue_poll_transition(
                            runtime_task_id_val=runtime_task_id_val,
                            task_id=task_id,
                            user_id=user_id,
                            session_factory=session_factory,
                            api_base=api_base,
                            httpx_async_client_factory=httpx_async_client_factory,
                            logger=logger,
                            build_not_found_progress_payload=(
                                build_not_found_progress_payload
                            ),
                            build_terminal_progress_payload=(
                                build_terminal_progress_payload
                            ),
                        )
                    )
                    for event in queue_events:
                        yield event
                    if became_running:
                        is_running = True
                    status_changed = status_signature != last_status_signature
                    status_check_interval = _next_task_stream_status_poll_interval(
                        current_interval=status_check_interval,
                        is_running=is_running,
                        status_changed=status_changed,
                    )
                    if status_signature is not None:
                        last_status_signature = status_signature
                    if should_stop:
                        break
                    last_status_check = current_time

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected for task %s", task_id)
        finally:
            if pubsub is not None:
                await _close_task_pubsub(
                    pubsub=pubsub,
                    channel=channel,
                    task_id=runtime_task_id_val,
                    logger=logger,
                )

    return EventSourceResponse(event_generator())
