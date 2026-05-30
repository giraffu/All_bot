import asyncio
import json
from typing import Any, Awaitable, Callable

from sse_starlette.sse import EventSourceResponse
from src.core.task_status_mapper import is_backend_terminal_status


async def _fetch_task_status_full(
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
) -> tuple[list[dict[str, str]], bool, bool]:
    events: list[dict[str, str]] = []
    initial_status = await _fetch_task_status_full(
        task_id=runtime_task_id_val,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
    )
    if not initial_status:
        return events, False, False
    if initial_status.get("not_found"):
        events.append(
            await _build_not_found_event(
                task_id=task_id,
                user_id=user_id,
                session_factory=session_factory,
                build_not_found_progress_payload=build_not_found_progress_payload,
            )
        )
        return events, False, True

    terminal_event, became_running, should_stop = _resolve_status_transition(
        status_data=initial_status,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event:
        events.append(terminal_event)
    return events, became_running, should_stop


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
) -> tuple[list[dict[str, str]], bool, bool]:
    events: list[dict[str, str]] = []
    status_data = await _fetch_task_status_full(
        task_id=runtime_task_id_val,
        api_base=api_base,
        httpx_async_client_factory=httpx_async_client_factory,
        logger=logger,
    )
    if not status_data:
        return events, False, False
    if status_data.get("not_found"):
        events.append(
            await _build_not_found_event(
                task_id=task_id,
                user_id=user_id,
                session_factory=session_factory,
                build_not_found_progress_payload=build_not_found_progress_payload,
            )
        )
        return events, False, True

    terminal_event, became_running, should_stop = _resolve_status_transition(
        status_data=status_data,
        task_id=task_id,
        build_terminal_progress_payload=build_terminal_progress_payload,
    )
    if terminal_event:
        events.append(terminal_event)
        return events, became_running, True
    if should_stop:
        return events, became_running, True

    queue_pos = status_data.get("queue_pos")
    if queue_pos is not None:
        events.append(
            _build_progress_event({"status": "pending", "queue_pos": queue_pos})
        )
    return events, became_running, False


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
) -> EventSourceResponse:
    async def event_generator():
        pubsub = redis.pubsub()
        runtime_task_id_val = runtime_task_id or task_id
        channel = f"comfy:task_events:{runtime_task_id_val}"
        await pubsub.subscribe(channel)

        try:
            yield _build_connected_event(task_id)
            is_running = False
            initial_events, became_running, should_stop = (
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
                )
            )
            for event in initial_events:
                yield event
            if became_running:
                is_running = True
            if should_stop:
                return

            last_queue_check = 0.0

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
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
                if should_stop:
                    break

                if not is_running:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_check > 5.0:
                        queue_events, became_running, should_stop = (
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
                        if should_stop:
                            break
                        last_queue_check = current_time

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected for task %s", task_id)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())
