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


def build_task_status_stream_response(
    *,
    task_id: str,
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
        channel = f"comfy:task_events:{task_id}"
        await pubsub.subscribe(channel)

        try:
            yield {
                "event": "connected",
                "data": json.dumps({"status": "listening", "task_id": task_id}),
            }

            initial_status = await _fetch_task_status_full(
                task_id=task_id,
                api_base=api_base,
                httpx_async_client_factory=httpx_async_client_factory,
                logger=logger,
            )
            is_running = False

            if initial_status:
                if initial_status.get("not_found"):
                    yield {
                        "event": "progress",
                        "data": json.dumps(
                            await build_not_found_progress_payload(
                                task_id,
                                user_id,
                                session_factory,
                            )
                        ),
                    }
                    return

                status_val = initial_status.get("status")
                if status_val == "running":
                    is_running = True
                else:
                    terminal_payload = build_terminal_progress_payload(
                        initial_status, task_id
                    )
                    if terminal_payload:
                        yield {
                            "event": "progress",
                            "data": json.dumps(terminal_payload),
                        }
                        return

            last_queue_check = 0.0

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    try:
                        parsed = json.loads(data)
                        task_status = parsed.get("status")
                        terminal_payload = build_terminal_progress_payload(
                            parsed, task_id
                        )
                        if terminal_payload:
                            parsed = terminal_payload

                        yield {"event": "progress", "data": json.dumps(parsed)}

                        if task_status == "running":
                            is_running = True
                        elif task_status in ["done", "error", "cancelled"]:
                            break
                    except json.JSONDecodeError:
                        yield {"event": "progress", "data": data}

                if not is_running:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_check > 5.0:
                        status_data = await _fetch_task_status_full(
                            task_id=task_id,
                            api_base=api_base,
                            httpx_async_client_factory=httpx_async_client_factory,
                            logger=logger,
                        )
                        if status_data:
                            if status_data.get("not_found"):
                                yield {
                                    "event": "progress",
                                    "data": json.dumps(
                                        await build_not_found_progress_payload(
                                            task_id,
                                            user_id,
                                            session_factory,
                                        )
                                    ),
                                }
                                break

                            status_val = status_data.get("status")
                            if status_val == "running":
                                is_running = True
                            else:
                                terminal_payload = build_terminal_progress_payload(
                                    status_data, task_id
                                )
                                if terminal_payload:
                                    yield {
                                        "event": "progress",
                                        "data": json.dumps(terminal_payload),
                                    }
                                    break

                                queue_pos = status_data.get("queue_pos")
                                if queue_pos is not None:
                                    yield {
                                        "event": "progress",
                                        "data": json.dumps(
                                            {
                                                "status": "pending",
                                                "queue_pos": queue_pos,
                                            }
                                        ),
                                    }
                        last_queue_check = current_time

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected for task %s", task_id)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())
