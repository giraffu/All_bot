import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agent_result_assets import resolve_history_result_asset, result_asset_priority


class TaskExecutionTimeoutError(TimeoutError):
    """Raised when ComfyUI does not produce history output before the hard deadline."""


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


async def _probe_history_result(
    *,
    comfy_client,
    execution,
    task_type: str | None,
    logger,
) -> bool:
    if not comfy_client or not execution.prompt_id:
        return False

    try:
        history = await comfy_client.get_history(execution.prompt_id)
    except Exception as exc:
        logger.warning(
            "History probe failed for prompt %s: %s",
            execution.prompt_id,
            exc,
        )
        return False

    history_result = resolve_history_result_asset(
        history,
        prompt_id=execution.prompt_id,
        task_id=execution.task_id,
        task_type=task_type,
    )
    if not history_result:
        return False

    execution.task_result = history_result["safe_name"]
    execution.task_result_priority = result_asset_priority(
        history_result,
        task_type=task_type,
    )
    execution.completed_event.set()
    logger.info(
        "History probe found completed result for task %s, prompt %s",
        execution.task_id,
        execution.prompt_id,
    )
    return True


async def wait_for_task_completion(
    *,
    task_id: str,
    execution,
    check_task_cancelled_func: Callable[[str], Awaitable[bool]],
    logger,
    comfy_client=None,
    task_type: str | None = None,
    history_probe_start_seconds: float = 45.0,
    history_probe_interval_seconds: float = 12.0,
    timeout_seconds: float = 1800.0,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    next_history_probe_at = loop.time() + history_probe_start_seconds
    while not execution.completed_event.is_set():
        if await check_task_cancelled_func(task_id):
            logger.info("Task %s was cancelled during execution wait.", task_id)
            return False

        now = loop.time()
        if now >= next_history_probe_at:
            if await _probe_history_result(
                comfy_client=comfy_client,
                execution=execution,
                task_type=task_type,
                logger=logger,
            ):
                break
            next_history_probe_at = now + history_probe_interval_seconds

        remaining = deadline - loop.time()
        if remaining <= 0:
            logger.warning(
                "Task execution timed out for %s after %.0fs, will attempt final history fallback.",
                task_id,
                timeout_seconds,
            )
            if await _probe_history_result(
                comfy_client=comfy_client,
                execution=execution,
                task_type=task_type,
                logger=logger,
            ):
                break
            raise TaskExecutionTimeoutError(
                "Task execution timed out for "
                f"{task_id} after {timeout_seconds:.0f}s without ComfyUI history result"
            )

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
