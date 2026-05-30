import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


async def submit_task_workflow(
    *,
    task_id: str,
    task_type: str,
    params: dict[str, Any],
    execution,
    patcher,
    comfy_client,
    wait_for_comfy_ready_func: Callable[..., Awaitable[None]],
    report_status_func: Callable[..., Awaitable[None]],
    agent_id: str,
    logger,
) -> None:
    workflow = patcher.load_workflow(task_type)
    if not workflow:
        raise ValueError(f"Workflow for {task_type} not found")

    patched_workflow = patcher.patch_workflow(task_type, workflow, params)
    client_id = f"agent_{agent_id}"
    await wait_for_comfy_ready_func(operation=f"submitting task {task_id}")
    execution.prompt_id = await comfy_client.queue_prompt(patched_workflow, client_id)
    logger.info(
        "Submitted task %s to ComfyUI, prompt_id: %s",
        task_id,
        execution.prompt_id,
    )
    await report_status_func(task_id, "running")


async def wait_for_task_completion(
    *,
    task_id: str,
    execution,
    check_task_cancelled_func: Callable[[str], Awaitable[bool]],
    logger,
    timeout_seconds: float = 600.0,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while not execution.completed_event.is_set():
        if await check_task_cancelled_func(task_id):
            logger.info("Task %s was cancelled during execution wait.", task_id)
            return False

        remaining = deadline - loop.time()
        if remaining <= 0:
            logger.warning(
                "Task execution timed out for %s, will attempt to fetch result from history.",
                task_id,
            )
            break

        try:
            await asyncio.wait_for(
                execution.completed_event.wait(),
                timeout=min(2.0, remaining),
            )
        except asyncio.TimeoutError:
            continue

    if execution.task_error:
        raise RuntimeError(execution.task_error)
    return True
