from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dashboard.backend.schemas import RefundTaskRequest, SyncLockRequest
from dashboard.backend.services.system_service import (
    clean_zombie_tasks_payload,
    get_active_bot_tasks_payload,
    get_bot_queue_payload,
    get_concurrency_stats_payload,
    get_system_status_payload,
    get_system_status_proxy_payload,
    get_system_workers_proxy_payload,
    get_task_status_proxy_payload,
    refund_bot_task_payload,
    stream_task_asset_proxy,
    sync_user_concurrency_payload,
)

router = APIRouter(prefix="/api", tags=["system"])


@router.post("/system/refund_bot_task")
async def refund_bot_task(req: RefundTaskRequest):
    """Force terminate a stuck task, refund credits and release concurrency lock."""
    return await refund_bot_task_payload(task_id=req.task_id)


@router.post("/system/clean_zombie_tasks")
async def clean_zombie_tasks():
    """Force clean all tasks older than 10 minutes (600s) and refund."""
    return await clean_zombie_tasks_payload()


@router.get("/health")
async def health_check(request: Request):
    health_state = getattr(request.app.state, "dashboard_health", {})
    database_ready = bool(health_state.get("database_ready"))
    startup_complete = bool(health_state.get("startup_complete"))

    payload = {
        "status": "ok" if database_ready and startup_complete else "degraded",
        "database_ready": database_ready,
        "startup_complete": startup_complete,
        "database_error": health_state.get("database_error"),
    }
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@router.post("/system/sync_user_concurrency")
async def sync_user_concurrency(req: SyncLockRequest):
    """Sync user's concurrency lock to match their actual active tasks count."""
    return await sync_user_concurrency_payload(user_id=req.user_id)


@router.get("/system/concurrency_stats")
async def get_concurrency_stats():
    """Get active concurrency locks and tasks per user."""
    return await get_concurrency_stats_payload()


@router.get("/system/active_bot_tasks")
async def get_active_bot_tasks():
    """Get active tasks tracked by bot in Redis, merged with user database info and realtime status"""
    return await get_active_bot_tasks_payload()


@router.get("/bot/queue")
async def get_bot_queue():
    """Get current bot queue status from image service"""
    return await get_bot_queue_payload()


@router.get("/status")
async def get_system_status():
    """Check status of ComfyUI backend"""
    return await get_system_status_payload()


@router.get("/system/status")
async def get_system_status_proxy():
    """聚合 Bot 活跃任务与中控状态，供仪表盘统一展示。"""
    return await get_system_status_proxy_payload()


@router.get("/system/workers")
async def get_system_workers_proxy():
    """Proxy system workers request to ComfyUI Middleware"""
    return await get_system_workers_proxy_payload()


@router.get("/status/{task_id}")
async def get_task_status_proxy(task_id: str):
    """Proxy task status request to ComfyUI Middleware"""
    return await get_task_status_proxy_payload(task_id=task_id)


@router.get("/image/{task_id}")
async def get_task_image_proxy(task_id: str):
    """Proxy image download request to ComfyUI Middleware"""
    return await stream_task_asset_proxy(
        task_id=task_id,
        asset_type="image",
        timeout=30.0,
        not_found_detail="Image not found",
    )


@router.get("/video/{task_id}")
async def get_task_video_proxy(task_id: str):
    """Proxy video download request to ComfyUI Middleware"""
    return await stream_task_asset_proxy(
        task_id=task_id,
        asset_type="video",
        timeout=60.0,
        not_found_detail="Video not found",
    )
