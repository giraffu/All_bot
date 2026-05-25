from fastapi import HTTPException, status


def parse_allowed_types(types: str | None) -> list[str] | None:
    if not types:
        return None
    return [task_type.strip() for task_type in types.split(",")]


async def bind_agent_task(
    *,
    queue_manager,
    task_id: str,
    agent_id: str,
) -> None:
    await queue_manager.bind_agent_task(task_id, agent_id)


async def clear_agent_current_task(
    *,
    queue_manager,
    agent_id: str,
) -> None:
    await queue_manager.clear_agent_current_task(agent_id)


async def pop_task_payload(*, types: str | None, queue_manager) -> dict:
    task_data = await queue_manager.dequeue_task(
        allowed_types=parse_allowed_types(types),
    )
    if not task_data:
        return {"task": None, "message": "No pending tasks"}

    task_id, _ = task_data
    task_details = await queue_manager.get_task_status(task_id)
    if not task_details:
        return {"task": None, "message": "Task details not found"}
    return {"task": task_details}


async def check_task_payload(*, task_id: str, queue_manager) -> dict:
    task_details = await queue_manager.get_task_status(task_id)
    if not task_details:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status": task_details.get("status"),
        "cancel_requested": queue_manager._as_bool(task_details.get("cancel_requested")),
    }


async def update_status_payload(
    *,
    task_id: str,
    agent_id: str,
    status: str,
    progress: float,
    error: str,
    queue_manager,
) -> dict:
    await bind_agent_task(
        queue_manager=queue_manager,
        task_id=task_id,
        agent_id=agent_id,
    )
    await queue_manager.update_task_heartbeat(task_id)

    if status == "running" and progress > 0:
        await queue_manager.update_progress(task_id, progress)
    elif status == "cancelled":
        await clear_agent_current_task(
            queue_manager=queue_manager,
            agent_id=agent_id,
        )
        await queue_manager.cancel_running_task(task_id)
    elif status == "failed":
        await clear_agent_current_task(
            queue_manager=queue_manager,
            agent_id=agent_id,
        )
        await queue_manager.fail_task(task_id, error)

    return {"status": "ok"}


async def complete_task_payload(*, task_id: str, agent_id: str, result: str, queue_manager) -> dict:
    await clear_agent_current_task(
        queue_manager=queue_manager,
        agent_id=agent_id,
    )
    await queue_manager.complete_task(task_id, result)
    return {"status": "ok"}


async def task_heartbeat_payload(*, task_id: str, agent_id: str | None, queue_manager) -> dict:
    await queue_manager.update_task_heartbeat(task_id)
    if agent_id:
        await bind_agent_task(
            queue_manager=queue_manager,
            task_id=task_id,
            agent_id=agent_id,
        )
    return {"status": "ok"}


async def heartbeat_payload(*, agent_id: str, types: str, status: str, queue_manager) -> dict:
    await queue_manager.update_agent_heartbeat(agent_id, types, status)
    return {"status": "ok"}


def verify_agent_token(*, authorization: str | None, agent_token: str | None, logger) -> bool:
    if not agent_token:
        logger.error("AGENT_SECRET_TOKEN is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent authentication is not configured",
        )
    if not authorization or authorization != f"Bearer {agent_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent token",
        )
    return True
