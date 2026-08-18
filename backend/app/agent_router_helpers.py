from fastapi import HTTPException, status


def parse_allowed_types(types: str | None) -> list[str] | None:
    if not types:
        return None
    parsed = [task_type.strip() for task_type in types.split(",") if task_type.strip()]
    return parsed or None


def parse_task_type_preferences(
    *,
    types: str | None,
    preferred_types: str | None,
) -> tuple[list[str] | None, list[str] | None]:
    allowed = parse_allowed_types(types)
    preferred = parse_allowed_types(preferred_types)
    if not preferred:
        return allowed, None
    if not allowed:
        raise HTTPException(
            status_code=422,
            detail="preferred_types requires non-empty types",
        )
    unsupported = sorted(set(preferred) - set(allowed))
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"preferred_types must be a subset of types: {', '.join(unsupported)}",
        )
    return allowed, preferred


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
    task_id: str | None = None,
) -> None:
    await queue_manager.clear_agent_current_task(agent_id, task_id=task_id)


async def pop_task_payload(
    *,
    types: str | None,
    preferred_types: str | None = None,
    queue_manager,
    agent_id: str | None = None,
    cancel_lock: bool = False,
) -> dict:
    allowed, preferred = parse_task_type_preferences(
        types=types,
        preferred_types=preferred_types,
    )
    if agent_id and hasattr(queue_manager, "is_agent_pop_enabled"):
        enabled, reason = await queue_manager.is_agent_pop_enabled(agent_id)
        if not enabled:
            return {
                "task": None,
                "message": f"Agent {agent_id} is not accepting new tasks: {reason}",
            }

    if agent_id and hasattr(queue_manager, "get_pending_agent_task_claim"):
        claimed_task_id = await queue_manager.get_pending_agent_task_claim(agent_id)
        if claimed_task_id:
            claimed_task = await queue_manager.get_task_status(claimed_task_id)
            if claimed_task and claimed_task.get("status") == "running":
                await queue_manager.update_task_heartbeat(claimed_task_id)
                return {"task": claimed_task}

    task_data = await queue_manager.dequeue_task(
        allowed_types=allowed,
        preferred_types=preferred,
        cancel_lock=cancel_lock,
    )
    if not task_data:
        return {"task": None, "message": "No pending tasks"}

    task_id, _ = task_data
    task_details = await queue_manager.get_task_status(task_id)
    if not task_details:
        return {"task": None, "message": "Task details not found"}
    if agent_id:
        await queue_manager.reserve_agent_task_delivery(task_id, agent_id)
    return {"task": task_details}


async def peek_task_payload(
    *,
    types: str | None,
    preferred_types: str | None = None,
    limit: int,
    queue_manager,
) -> dict:
    allowed, preferred = parse_task_type_preferences(
        types=types,
        preferred_types=preferred_types,
    )
    tasks = await queue_manager.peek_pending_tasks(
        allowed_types=allowed,
        preferred_types=preferred,
        limit=max(1, limit),
    )
    if not tasks:
        return {"task": None, "message": "No pending tasks"}
    return {"task": tasks[0]}


async def check_task_payload(*, task_id: str, queue_manager) -> dict:
    task_details = await queue_manager.get_task_status(task_id)
    if not task_details:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status": task_details.get("status"),
        "cancel_requested": queue_manager._as_bool(task_details.get("cancel_requested")),
        "cancel_locked": queue_manager._as_bool(task_details.get("cancel_locked")),
        "execution_phase": task_details.get("execution_phase") or "",
    }


async def update_status_payload(
    *,
    task_id: str,
    agent_id: str,
    status: str,
    progress: float,
    error: str,
    queue_manager,
    execution_phase: str | None = None,
    cancel_locked: bool | None = None,
    set_current: bool = True,
) -> dict:
    if status in {"failed", "cancelled"}:
        await queue_manager.record_task_worker(task_id, agent_id)
    elif set_current:
        await bind_agent_task(
            queue_manager=queue_manager,
            task_id=task_id,
            agent_id=agent_id,
        )
    else:
        await queue_manager.record_task_worker(task_id, agent_id)
    await queue_manager.update_task_heartbeat(task_id)

    if status == "running":
        if execution_phase is not None or cancel_locked is not None:
            await queue_manager.update_task_runtime_metadata(
                task_id,
                progress=progress if progress > 0 else None,
                execution_phase=execution_phase,
                cancel_locked=cancel_locked,
            )
        elif progress > 0:
            await queue_manager.update_progress(task_id, progress)
    elif status == "cancelled":
        await clear_agent_current_task(
            queue_manager=queue_manager,
            agent_id=agent_id,
            task_id=task_id,
        )
        await queue_manager.cancel_running_task(task_id)
    elif status == "failed":
        await clear_agent_current_task(
            queue_manager=queue_manager,
            agent_id=agent_id,
            task_id=task_id,
        )
        await queue_manager.fail_task(task_id, error)

    return {"status": "ok"}


async def complete_task_payload(
    *,
    task_id: str,
    agent_id: str,
    result: str,
    extra_outputs: dict | None = None,
    result_asset: dict | None = None,
    extra_output_assets: dict | None = None,
    result_kind: str | None = None,
    result_text: str | None = None,
    result_meta: dict | None = None,
    minio_client=None,
    result_bucket: str = "",
    allow_legacy_completion: bool = True,
    promote_completion_assets_func=None,
    queue_manager,
) -> dict:
    if promote_completion_assets_func is None:
        from app.result_storage import promote_completion_assets

        promote_completion_assets_func = promote_completion_assets
    promoted = await promote_completion_assets_func(
        task_id=task_id,
        result_path=result,
        extra_outputs=extra_outputs,
        result_asset=result_asset,
        extra_output_assets=extra_output_assets,
        minio_client=minio_client,
        bucket=result_bucket,
        allow_legacy_completion=(allow_legacy_completion or result_kind == "text"),
    )
    result = promoted.result_path
    extra_outputs = promoted.extra_outputs
    await queue_manager.record_task_worker(task_id, agent_id)
    await clear_agent_current_task(
        queue_manager=queue_manager,
        agent_id=agent_id,
        task_id=task_id,
    )
    completion_kwargs = {"extra_outputs": extra_outputs}
    if promoted.result_asset is not None:
        completion_kwargs["result_asset"] = promoted.result_asset
    if promoted.extra_output_assets is not None:
        completion_kwargs["extra_output_assets"] = promoted.extra_output_assets
    if result_kind is not None:
        completion_kwargs["result_kind"] = result_kind
    if result_text is not None:
        completion_kwargs["result_text"] = result_text
    if result_meta is not None:
        completion_kwargs["result_meta"] = result_meta
    await queue_manager.complete_task(task_id, result, **completion_kwargs)
    return {"status": "ok"}


async def append_text_delta_payload(
    *,
    task_id: str,
    agent_id: str,
    attempt_id: str,
    sequence: int,
    field: str,
    delta: str,
    queue_manager,
) -> dict:
    return await queue_manager.append_task_text_delta(
        task_id=task_id,
        agent_id=agent_id,
        attempt_id=attempt_id,
        sequence=sequence,
        field=field,
        delta=delta,
    )


async def task_heartbeat_payload(*, task_id: str, agent_id: str | None, queue_manager) -> dict:
    await queue_manager.update_task_heartbeat(task_id)
    if agent_id:
        await bind_agent_task(
            queue_manager=queue_manager,
            task_id=task_id,
            agent_id=agent_id,
        )
    return {"status": "ok"}


async def heartbeat_payload(
    *,
    agent_id: str,
    types: str,
    status: str,
    queue_manager,
    health_reason: str = "",
    last_error: str = "",
    last_error_at=None,
    consecutive_failures=None,
    quarantined_until=None,
    metadata: dict | None = None,
) -> dict:
    await queue_manager.update_agent_heartbeat(
        agent_id,
        types,
        status,
        health_reason=health_reason,
        last_error=last_error,
        last_error_at=last_error_at,
        consecutive_failures=consecutive_failures,
        quarantined_until=quarantined_until,
        metadata=metadata,
    )
    return {"status": "ok"}


async def set_agent_control_payload(
    *,
    agent_id: str,
    state: str,
    reason: str,
    ttl_seconds: int | None,
    queue_manager,
) -> dict:
    return await queue_manager.set_agent_control_state(
        agent_id,
        state,
        reason=reason,
        ttl_seconds=ttl_seconds,
    )


async def get_agent_control_payload(*, agent_id: str, queue_manager) -> dict:
    control = await queue_manager.get_agent_control_state(agent_id)
    return {"agent_id": agent_id, **control}


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
