import asyncio
import json
from typing import Any, Awaitable, Callable

from sse_starlette.sse import EventSourceResponse


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


def _extract_message_payload(message_data: Any) -> str:
    if isinstance(message_data, bytes):
        return message_data.decode("utf-8")
    return message_data


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

            initial_status = await _fetch_task_status_full(
                task_id=runtime_task_id_val,
                api_base=api_base,
                httpx_async_client_factory=httpx_async_client_factory,
                logger=logger,
            )
            is_running = False

            if initial_status:
                if initial_status.get("not_found"):
                    yield await _build_not_found_event(
                        task_id=task_id,
                        user_id=user_id,
                        session_factory=session_factory,
                        build_not_found_progress_payload=build_not_found_progress_payload,
                    )
                    return

                status_val = initial_status.get("status")
                if status_val == "running":
                    is_running = True
                else:
                    terminal_event = _build_terminal_event(
                        status_data=initial_status,
                        task_id=task_id,
                        build_terminal_progress_payload=build_terminal_progress_payload,
                    )
                    if terminal_event:
                        yield terminal_event
                        return

            last_queue_check = 0.0

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message:
                    data = _extract_message_payload(message["data"])

                    try:
                        parsed = json.loads(data)
                        task_status = parsed.get("status")
                        terminal_event = _build_terminal_event(
                            status_data=parsed,
                            task_id=task_id,
                            build_terminal_progress_payload=build_terminal_progress_payload,
                        )
                        if terminal_event:
                            yield terminal_event
                        else:
                            yield _build_progress_event(parsed)

                        if task_status == "running":
                            is_running = True
                        elif task_status in ["done", "error", "cancelled"]:
                            break
                    except json.JSONDecodeError:
                        yield _build_progress_event(data)

                if not is_running:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_check > 5.0:
                        status_data = await _fetch_task_status_full(
                            task_id=runtime_task_id_val,
                            api_base=api_base,
                            httpx_async_client_factory=httpx_async_client_factory,
                            logger=logger,
                        )
                        if status_data:
                            if status_data.get("not_found"):
                                yield await _build_not_found_event(
                                    task_id=task_id,
                                    user_id=user_id,
                                    session_factory=session_factory,
                                    build_not_found_progress_payload=(
                                        build_not_found_progress_payload
                                    ),
                                )
                                break

                            status_val = status_data.get("status")
                            if status_val == "running":
                                is_running = True
                            else:
                                terminal_event = _build_terminal_event(
                                    status_data=status_data,
                                    task_id=task_id,
                                    build_terminal_progress_payload=(
                                        build_terminal_progress_payload
                                    ),
                                )
                                if terminal_event:
                                    yield terminal_event
                                    break

                                queue_pos = status_data.get("queue_pos")
                                if queue_pos is not None:
                                    yield _build_progress_event(
                                        {
                                            "status": "pending",
                                            "queue_pos": queue_pos,
                                        }
                                    )
                        last_queue_check = current_time

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected for task %s", task_id)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())
