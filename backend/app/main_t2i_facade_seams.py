from contextlib import asynccontextmanager

from app.models import TaskType
from fastapi import HTTPException


@asynccontextmanager
async def optional_t2i_task_subscription_seam(
    *,
    async_mode: bool,
    queue_manager,
    task_id: str,
    optional_t2i_task_subscription_helper,
    subscribe_task_events_func,
    close_task_event_subscription_func,
):
    async with optional_t2i_task_subscription_helper(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        subscribe_task_events_func=subscribe_task_events_func,
        close_task_event_subscription_func=close_task_event_subscription_func,
    ) as subscription:
        yield subscription


async def enqueue_t2i_task_seam(
    *,
    queue_manager,
    task_id: str,
    params: dict,
    priority: int,
    request_id: str,
    logger,
    enqueue_t2i_task_helper,
) -> None:
    await enqueue_t2i_task_helper(
        queue_manager=queue_manager,
        task_type=TaskType.T2I_PORNMASTER_TURBO,
        task_id=task_id,
        params=params,
        priority=priority,
        request_id=request_id,
        logger=logger,
    )


async def get_immediate_t2i_terminal_response_seam(
    *,
    queue_manager,
    task_id: str,
    request_id: str,
    get_immediate_t2i_terminal_response_helper,
    build_terminal_response_func,
):
    return await get_immediate_t2i_terminal_response_helper(
        queue_manager=queue_manager,
        task_id=task_id,
        request_id=request_id,
        build_terminal_response_func=build_terminal_response_func,
    )


async def wait_for_t2i_sync_result_seam(
    *,
    pubsub,
    task_id: str,
    request_id: str,
    queue_manager,
    timeout: int,
    logger,
    wait_for_t2i_sync_result_helper,
    get_immediate_response_func,
    wait_for_terminal_response_func,
):
    return await wait_for_t2i_sync_result_helper(
        pubsub=pubsub,
        task_id=task_id,
        request_id=request_id,
        queue_manager=queue_manager,
        timeout=timeout,
        get_immediate_response_func=get_immediate_response_func,
        wait_for_terminal_response_func=wait_for_terminal_response_func,
        logger=logger,
    )


async def submit_t2i_task_request_seam(
    *,
    async_mode: bool,
    queue_manager,
    task_id: str,
    params: dict[str, str],
    task_priority: int,
    request_id: str,
    response_cls,
    logger,
    submit_t2i_task_request_helper,
    optional_subscription_func,
    enqueue_t2i_task_func,
    wait_for_sync_result_func,
):
    return await submit_t2i_task_request_helper(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        params=params,
        task_priority=task_priority,
        request_id=request_id,
        response_cls=response_cls,
        optional_subscription_func=optional_subscription_func,
        enqueue_t2i_task_func=enqueue_t2i_task_func,
        wait_for_sync_result_func=wait_for_sync_result_func,
        logger=logger,
    )


async def create_t2i_pornmaster_turbo_task_seam(
    *,
    request: dict,
    queue_manager,
    async_mode: bool,
    priority: int,
    request_id: str,
    logger,
    prepare_t2i_request_payload_func,
    submit_t2i_task_request_func,
):
    logger.info(f"[{request_id}] Received T2I task request: {request}")

    try:
        task_id, task_priority, params = prepare_t2i_request_payload_func(
            request,
            default_priority=priority,
        )
    except HTTPException:
        logger.error(f"[{request_id}] Invalid prompt: {request.get('prompt')}")
        raise

    return await submit_t2i_task_request_func(
        async_mode=async_mode,
        queue_manager=queue_manager,
        task_id=task_id,
        params=params,
        task_priority=task_priority,
        request_id=request_id,
    )
