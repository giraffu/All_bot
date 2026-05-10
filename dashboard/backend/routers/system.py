import logging

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from config import API_BASE, STATUS_ENDPOINT
from src.core.task_core import force_terminate_task, get_system_task_stats
from src.core.task_core import sync_user_concurrency as core_sync_user_concurrency
from src.database.models import User
from src.services.image_service import image_service

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger("dashboard.system")


class RefundTaskRequest(BaseModel):
    task_id: str


@router.post("/system/refund_bot_task")
async def refund_bot_task(req: RefundTaskRequest):
    """Force terminate a stuck task, refund credits and release concurrency lock."""
    try:
        from src.services.permission_service import permission_service

        task_id = req.task_id
        tasks, _ = await get_system_task_stats()
        if not tasks or task_id not in tasks:
            raise HTTPException(
                status_code=404, detail="Task not found in Redis active tasks"
            )

        task = tasks[task_id]
        user_id = task.get("user_id")
        username = task.get("username", "Unknown")
        cost = task.get("cost", 0)

        # 1. Refund
        if cost > 0 and user_id:
            await permission_service.increment_quota(
                user_id, cost=-cost, username=username, task_type="refund_admin_force"
            )

        # 2. Release lock and remove task via Core API
        await force_terminate_task(task_id, user_id=user_id)

        return {
            "status": "success",
            "message": f"Task {task_id} terminated and {cost} credits refunded.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refunding bot task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system/clean_zombie_tasks")
async def clean_zombie_tasks():
    """Force clean all tasks older than 10 minutes (600s) and refund."""
    try:
        import time

        from src.services.permission_service import permission_service

        tasks, _ = await get_system_task_stats()
        if not tasks:
            return {
                "status": "success",
                "message": "No active tasks found.",
                "removed": 0,
            }

        removed = 0
        now = time.time()

        for task_id, task in tasks.items():
            age = now - task.get("created_at", now)
            if age > 7200:  # 超过2小时，认为可能卡死
                user_id = task.get("user_id")
                username = task.get("username", "Unknown")
                cost = task.get("cost", 0)

                if cost > 0 and user_id:
                    try:
                        await permission_service.increment_quota(
                            user_id,
                            cost=-cost,
                            username=username,
                            task_type="refund_admin_force_cleanup",
                        )
                    except Exception as e:
                        logger.error(
                            f"Error refunding during cleanup for user {user_id}: {e}"
                        )

                await force_terminate_task(task_id, user_id=user_id)
                removed += 1

        return {
            "status": "success",
            "message": f"Cleaned up {removed} zombie tasks.",
            "removed": removed,
        }
    except Exception as e:
        logger.error(f"Error cleaning zombie tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    return {"status": "ok"}


class SyncLockRequest(BaseModel):
    user_id: int


@router.post("/system/sync_user_concurrency")
async def sync_user_concurrency(req: SyncLockRequest):
    """Sync user's concurrency lock to match their actual active tasks count."""
    try:
        active_tasks, concurrencies = await get_system_task_stats()
        actual_count = sum(
            1 for t in active_tasks.values() if t.get("user_id") == req.user_id
        )

        current_lock = concurrencies.get(req.user_id, 0)

        if current_lock > actual_count:
            await core_sync_user_concurrency(req.user_id, actual_count)
            return {
                "status": "success",
                "message": f"用户 {req.user_id} 并发锁已从 {current_lock} 修复为 {actual_count}",
            }
        else:
            return {"status": "info", "message": "无需修复，锁数量未超出真实任务数"}
    except Exception as e:
        logger.error(f"Error syncing concurrency lock for user {req.user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/concurrency_stats")
async def get_concurrency_stats():
    """Get active concurrency locks and tasks per user."""
    from src.database.core import AsyncSessionLocal

    try:
        active_tasks, concurrencies = await get_system_task_stats()

        user_active_tasks = {}
        user_names = {}
        for task_id, task in active_tasks.items():
            uid = task.get("user_id")
            if uid:
                user_active_tasks[uid] = user_active_tasks.get(uid, 0) + 1
                if task.get("username"):
                    user_names[uid] = task.get("username")

        all_uids = set(concurrencies.keys()).union(set(user_active_tasks.keys()))

        missing_uids = list(all_uids - set(user_names.keys()))
        if missing_uids:
            async with AsyncSessionLocal() as db:
                stmt = select(User.id, User.username).where(User.id.in_(missing_uids))
                result = await db.execute(stmt)
                for row in result.all():
                    user_names[row.id] = row.username

        stats = []
        for uid in all_uids:
            stats.append(
                {
                    "user_id": uid,
                    "username": user_names.get(uid, f"User_{uid}"),
                    "concurrency_locks": concurrencies.get(uid, 0),
                    "active_tasks": user_active_tasks.get(uid, 0),
                }
            )

        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"Error getting concurrency stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/active_bot_tasks")
async def get_active_bot_tasks():
    """Get active tasks tracked by bot in Redis, merged with user database info and realtime status"""
    from src.database.core import AsyncSessionLocal

    try:
        tasks, _ = await get_system_task_stats()

        if tasks:
            user_ids = [
                task.get("user_id") for task in tasks.values() if task.get("user_id")
            ]
            user_info = {}
            if user_ids:
                async with AsyncSessionLocal() as db:
                    stmt = select(
                        User.id, User.user_group, User.current_identity
                    ).where(User.id.in_(user_ids))
                    result = await db.execute(stmt)
                    user_info = {
                        row.id: {
                            "user_group": row.user_group,
                            "current_identity": row.current_identity,
                        }
                        for row in result.all()
                    }

            backend_statuses = {}
            try:
                import asyncio

                from src.api_client import api_client

                tasks_to_check = [
                    task.get("backend_task_id")
                    for task in tasks.values()
                    if task.get("backend_task_id")
                ]

                async def fetch_status(backend_id):
                    try:
                        url = f"{API_BASE}/status/{backend_id}"
                        r = await api_client._request("GET", url, timeout=2)
                        return backend_id, r.json()
                    except Exception:
                        return backend_id, None

                if tasks_to_check:
                    results = await asyncio.gather(
                        *(fetch_status(tid) for tid in tasks_to_check[:20])
                    )
                    for backend_id, status_data in results:
                        if status_data:
                            backend_statuses[backend_id] = status_data
            except Exception as e:
                logger.warning(f"Could not fetch executing tasks from backend: {e}")

            for task_id, task in tasks.items():
                uid = task.get("user_id")
                if uid in user_info:
                    task["user_group"] = user_info[uid]["user_group"]
                    task["user_identity"] = user_info[uid]["current_identity"]
                else:
                    task["user_group"] = "未知"
                    task["user_identity"] = "外门弟子"

                    backend_id = task.get("backend_task_id")
                    status_data = backend_statuses.get(backend_id)

                    if status_data:
                        state = status_data.get("status")
                        task["execution_status"] = state
                        if state == "running":
                            task["queue_position"] = "生成中"
                        elif state == "pending":
                            task["queue_position"] = status_data.get("queue_pos", "-")
                        elif state == "done":
                            task["queue_position"] = "已完成"
                        elif state == "error":
                            task["queue_position"] = "异常"
                        elif state == "cancelled":
                            task["queue_position"] = "已取消"
                        else:
                            task["queue_position"] = "未知"
                    elif backend_id:
                        task["execution_status"] = "pending"
                        task["queue_position"] = "-"
                    else:
                        task["execution_status"] = "submitting"
                        task["queue_position"] = "提交中"

        return {"status": "success", "tasks": tasks, "count": len(tasks)}
    except Exception as e:
        logger.error(f"Error getting active bot tasks from Redis: {e}")
        return {"status": "error", "message": str(e), "tasks": {}, "count": 0}


@router.get("/bot/queue")
async def get_bot_queue():
    """Get current bot queue status from image service"""
    try:
        status = await image_service.get_queue_info()
        return status or {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
        }
    except Exception as e:
        logger.error(f"Error getting bot queue status: {e}")
        return {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
            "error": str(e),
        }


@router.get("/status")
async def get_system_status():
    """Check status of ComfyUI backend"""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(STATUS_ENDPOINT, timeout=5.0)
            return {
                "comfyui": "online" if response.status_code == 200 else "error",
                "details": response.json()
                if response.status_code == 200
                else str(response.status_code),
            }
    except Exception as e:
        return {"comfyui": "offline", "error": str(e)}


@router.get("/system/status")
async def get_system_status_proxy():
    """Proxy system status request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/system/status"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
            else:
                data = {
                    "queue_size": 0,
                    "queue_by_type": {},
                    "active_workers": 0,
                    "comfy_online": False,
                    "error": f"Middleware returned {response.status_code}",
                }
    except Exception as e:
        logger.error(f"Error proxying system status: {e}")
        data = {
            "queue_size": 0,
            "queue_by_type": {},
            "active_workers": 0,
            "comfy_online": False,
            "error": str(e),
        }

    # 获取并注入并发锁数据
    try:
        _, concurrencies = await get_system_task_stats()
        data["concurrency_locks"] = sum(concurrencies.values())
        data["concurrency_details"] = concurrencies
    except Exception as e:
        logger.error(f"Error getting concurrency locks: {e}")
        data["concurrency_locks"] = 0
        data["concurrency_details"] = {}

    return data


@router.get("/system/workers")
async def get_system_workers_proxy():
    """Proxy system workers request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/system/workers"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "workers": [],
                    "count": 0,
                    "error": f"Middleware returned {response.status_code}",
                }
    except Exception as e:
        logger.error(f"Error proxying system workers: {e}")
        return {"workers": [], "count": 0, "error": str(e)}


@router.get("/status/{task_id}")
async def get_task_status_proxy(task_id: str):
    """Proxy task status request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/status/{task_id}"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code, detail="Task not found or error"
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/image/{task_id}")
async def get_task_image_proxy(task_id: str):
    """Proxy image download request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/image/{task_id}"

        client = httpx.AsyncClient(trust_env=False)
        req = client.build_request("GET", url, timeout=30.0)
        r = await client.send(req, stream=True)

        if r.status_code != 200:
            await r.aclose()
            await client.aclose()
            raise HTTPException(status_code=r.status_code, detail="Image not found")

        async def iter_file():
            try:
                async for chunk in r.aiter_bytes():
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        return StreamingResponse(iter_file(), media_type=r.headers.get("content-type"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/video/{task_id}")
async def get_task_video_proxy(task_id: str):
    """Proxy video download request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/video/{task_id}"

        client = httpx.AsyncClient(trust_env=False)
        req = client.build_request("GET", url, timeout=60.0)
        r = await client.send(req, stream=True)

        if r.status_code != 200:
            await r.aclose()
            await client.aclose()
            raise HTTPException(status_code=r.status_code, detail="Video not found")

        async def iter_file():
            try:
                async for chunk in r.aiter_bytes():
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        return StreamingResponse(iter_file(), media_type=r.headers.get("content-type"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying video: {e}")
        raise HTTPException(status_code=500, detail=str(e))
