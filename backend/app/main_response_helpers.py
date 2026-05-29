import os
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.models import SystemStatusResponse, SystemWorkersResponse, TaskStatusResponse
from minio import Minio


def build_result_url(*, result_path: str, settings) -> str:
    protocol = "https" if settings.minio_secure else "http"
    return (
        f"{protocol}://{settings.minio_endpoint}/"
        f"{settings.minio_result_bucket}/{result_path}"
    )


async def build_task_status_response(
    *,
    task_id: str,
    queue_manager,
    include_image_url: bool = False,
    include_task_type: bool = False,
    build_result_url_func,
) -> TaskStatusResponse:
    task = await queue_manager.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task.get("status")
    queue_pos = None
    queue_remaining = None
    if status == "pending":
        queue_pos = await queue_manager.get_queue_position(task_id)
        queue_remaining = queue_pos if queue_pos is not None else 0

    result_path = task.get("result_path")
    extra_outputs = queue_manager._maybe_parse_json_dict(task.get("extra_outputs"))
    response_kwargs = {
        "status": status,
        "queue_pos": queue_pos,
        "queue_remaining": queue_remaining,
        "progress": float(task.get("progress", 0.0)),
        "error": task.get("error_msg"),
        "result_path": result_path,
        "extra_outputs": extra_outputs,
        "cancel_requested": queue_manager._as_bool(task.get("cancel_requested")),
        "cancel_requested_at": (
            float(task["cancel_requested_at"])
            if task.get("cancel_requested_at")
            else None
        ),
    }
    if include_image_url and status == "done" and result_path:
        response_kwargs["image_url"] = build_result_url_func(result_path)
    if include_task_type:
        response_kwargs["task_type"] = task.get("type")
    return TaskStatusResponse(**response_kwargs)


async def serve_task_result_file(
    *,
    task_id: str,
    ready_error_detail: str,
    queue_manager,
    minio_client: Optional[Minio],
    settings,
    logger,
) -> FileResponse:
    task = await queue_manager.get_task_status(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail=ready_error_detail)

    result_path = task.get("result_path")
    if not result_path:
        raise HTTPException(status_code=404, detail="Result path missing")
    if not minio_client:
        raise HTTPException(status_code=500, detail="MinIO client not initialized")

    import tempfile

    try:
        logger.info(
            "Fetching %s from MinIO bucket %s",
            result_path,
            settings.minio_result_bucket,
        )
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        minio_client.fget_object(settings.minio_result_bucket, result_path, temp_path)
        background_tasks = BackgroundTasks()
        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, background=background_tasks)
    except Exception as exc:
        logger.error(f"MinIO download failed: {exc}")
        raise HTTPException(status_code=404, detail="File not found in storage")


async def build_system_workers_response(queue_manager) -> SystemWorkersResponse:
    workers = await queue_manager.get_all_workers()
    return SystemWorkersResponse(workers=workers, count=len(workers))


async def build_system_status_response(queue_manager) -> SystemStatusResponse:
    queue_size = await queue_manager.get_queue_size()
    active_workers = await queue_manager.get_active_workers_count()
    queue_by_type = await queue_manager.get_queue_metrics_by_type()
    return SystemStatusResponse(
        queue_size=queue_size,
        queue_by_type=queue_by_type,
        active_workers=active_workers,
        comfy_online=active_workers > 0,
    )


async def cancel_task_or_404(queue_manager, task_id: str):
    result = await queue_manager.cancel_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
