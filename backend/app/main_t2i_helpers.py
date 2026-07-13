import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import HTTPException
from app.queue_manager import TaskAdmissionConflictError


def build_task_event_channel(task_id: str) -> str:
    return f"comfy:task_events:{task_id}"


def validate_t2i_prompt(prompt: object) -> str:
    if not isinstance(prompt, str):
        raise HTTPException(
            status_code=400, detail="prompt is required and length must be 1-2048"
        )
    normalized_prompt = prompt.strip()
    if len(normalized_prompt) < 1 or len(normalized_prompt) > 2048:
        raise HTTPException(
            status_code=400, detail="prompt is required and length must be 1-2048"
        )
    return normalized_prompt


def resolve_t2i_priority(request_body: dict, default_priority: int) -> int:
    return request_body.get("priority", default_priority)


def prepare_t2i_request_payload(
    request_body: dict,
    *,
    default_priority: int,
    uuid_factory,
    validate_prompt_func,
    resolve_priority_func,
) -> tuple[str, int, dict[str, str]]:
    prompt = validate_prompt_func(request_body.get("prompt"))
    task_priority = resolve_priority_func(request_body, default_priority)
    task_id = str(uuid_factory())
    return task_id, task_priority, {"prompt": prompt}


def build_t2i_success_response(*, task_id: str, result_path: str, response_cls, build_result_url_func):
    return response_cls(task_id=task_id, image_url=build_result_url_func(result_path))


def build_t2i_terminal_response(
    *,
    task_id: str,
    status: str | None,
    result_path: str | None,
    error_msg: str | None,
    request_id: str,
    response_cls,
    build_result_url_func,
    logger,
):
    if status == "done":
        image_url = build_result_url_func(result_path)
        logger.info(f"[{request_id}] Task {task_id} completed: {image_url}")
        return build_t2i_success_response(
            task_id=task_id,
            result_path=result_path,
            response_cls=response_cls,
            build_result_url_func=build_result_url_func,
        )
    if status == "error":
        message = error_msg or "Unknown error"
        logger.error(f"[{request_id}] Task {task_id} failed: {message}")
        raise HTTPException(status_code=500, detail=f"Task failed: {message}")
    return None


def decode_t2i_pubsub_message(data: str | bytes) -> dict | None:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


async def wait_for_t2i_terminal_response(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    timeout: int,
    decode_message_func,
    build_terminal_response_func,
):
    async def listen_for_result():
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            parsed = decode_message_func(message["data"])
            if not parsed:
                continue
            response = build_terminal_response_func(
                task_id=task_id,
                status=parsed.get("status"),
                result_path=parsed.get("result_path"),
                error_msg=parsed.get("error_msg"),
                request_id=request_id,
            )
            if response:
                return response

    return await asyncio.wait_for(listen_for_result(), timeout=timeout)


async def subscribe_task_events(*, queue_manager, task_id: str, build_channel_func):
    pubsub = queue_manager.redis.pubsub()
    channel = build_channel_func(task_id)
    await pubsub.subscribe(channel)
    return pubsub, channel


async def close_task_event_subscription(*, pubsub, channel: str) -> None:
    await pubsub.unsubscribe(channel)
    await pubsub.close()


@asynccontextmanager
async def optional_t2i_task_subscription(
    *,
    async_mode: bool,
    queue_manager,
    task_id: str,
    subscribe_task_events_func,
    close_task_event_subscription_func,
):
    if async_mode:
        yield None, None
        return

    pubsub, channel = await subscribe_task_events_func(queue_manager, task_id)
    try:
        yield pubsub, channel
    finally:
        await close_task_event_subscription_func(pubsub=pubsub, channel=channel)


async def enqueue_t2i_task(
    *,
    queue_manager,
    task_type,
    task_id: str,
    params: dict,
    priority: int,
    request_id: str,
    logger,
) -> None:
    try:
        await queue_manager.enqueue_task(task_type, params, priority, task_id)
        logger.info(f"[{request_id}] Task enqueued: {task_id} with priority {priority}")
    except TaskAdmissionConflictError as exc:
        logger.warning(f"[{request_id}] Conflicting task admission: {task_id}")
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"[{request_id}] Failed to enqueue task: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


async def get_immediate_t2i_terminal_response(
    *,
    queue_manager,
    task_id: str,
    request_id: str,
    build_terminal_response_func,
):
    task_status = await queue_manager.get_task_status(task_id)
    if not task_status:
        return None
    return build_terminal_response_func(
        task_id=task_id,
        status=task_status.get("status"),
        result_path=task_status.get("result_path"),
        error_msg=task_status.get("error_msg"),
        request_id=request_id,
    )


async def wait_for_t2i_sync_result(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    queue_manager,
    timeout: int = 60,
    get_immediate_response_func,
    wait_for_terminal_response_func,
    logger,
):
    immediate_response = await get_immediate_response_func(
        queue_manager=queue_manager,
        task_id=task_id,
        request_id=request_id,
    )
    if immediate_response:
        return immediate_response

    try:
        return await wait_for_terminal_response_func(
            pubsub=pubsub,
            task_id=task_id,
            request_id=request_id,
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        logger.error(f"[{request_id}] Task {task_id} timed out")
        raise HTTPException(status_code=504, detail="Task execution timed out") from exc


async def submit_t2i_task_request(
    *,
    async_mode: bool,
    queue_manager,
    task_id: str,
    params: dict[str, str],
    task_priority: int,
    request_id: str,
    response_cls,
    optional_subscription_func,
    enqueue_t2i_task_func,
    wait_for_sync_result_func,
    logger,
):
    async with optional_subscription_func(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
    ) as (pubsub, _channel):
        await enqueue_t2i_task_func(
            queue_manager=queue_manager,
            task_id=task_id,
            params=params,
            priority=task_priority,
            request_id=request_id,
        )

        if not async_mode:
            logger.info(f"[{request_id}] Sync mode: waiting for task {task_id}")
            return await wait_for_sync_result_func(
                pubsub=pubsub,
                task_id=task_id,
                request_id=request_id,
                queue_manager=queue_manager,
            )

    return response_cls(task_id=task_id)
