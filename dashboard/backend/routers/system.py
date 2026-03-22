from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import logging
from src.database.core import get_db
from src.database.models import User
from src.services.redis_client import redis_client
from src.services.image_service import image_service
from config import API_BASE, STATUS_ENDPOINT
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger("dashboard.system")

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/system/active_bot_tasks")
async def get_active_bot_tasks(db: AsyncSession = Depends(get_db)):
    """Get active tasks tracked by bot in Redis, merged with user database info and realtime status"""
    try:
        tasks = await redis_client.get_active_tasks()
        
        if tasks:
            user_ids = [task.get("user_id") for task in tasks.values() if task.get("user_id")]
            if user_ids:
                stmt = select(User.id, User.user_group, User.current_identity).where(User.id.in_(user_ids))
                result = await db.execute(stmt)
                user_info = {row.id: {"user_group": row.user_group, "current_identity": row.current_identity} for row in result.all()}
                
                executing_ids = []
                try:
                    import asyncio
                    from src.api_client import api_client
                    
                    tasks_to_check = [task.get("backend_task_id") for task in tasks.values() if task.get("backend_task_id")]
                    
                    async def fetch_status(backend_id):
                        try:
                            url = f"{API_BASE}/status/{backend_id}"
                            r = await api_client._request("GET", url, timeout=2)
                            return backend_id, r.json()
                        except Exception:
                            return backend_id, None

                    if tasks_to_check:
                        results = await asyncio.gather(*(fetch_status(tid) for tid in tasks_to_check[:20]))
                        for backend_id, status_data in results:
                            if status_data:
                                state = status_data.get("status")
                                if state == "generating" or (state and state not in ["pending", "done", "error"]):
                                    executing_ids.append(backend_id)
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
                    if backend_id and backend_id in executing_ids:
                        task["execution_status"] = "generating"
                    elif backend_id:
                        task["execution_status"] = "pending"
                    else:
                        task["execution_status"] = "submitting"

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
            "img2video_active_tasks": 0
        }
    except Exception as e:
        logger.error(f"Error getting bot queue status: {e}")
        return {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
            "error": str(e)
        }

@router.get("/status")
async def get_system_status():
    """Check status of ComfyUI backend"""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(STATUS_ENDPOINT, timeout=5.0)
            return {"comfyui": "online" if response.status_code == 200 else "error", "details": response.json() if response.status_code == 200 else str(response.status_code)}
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
                return response.json()
            else:
                return {
                    "queue_size": 0,
                    "queue_by_type": {},
                    "active_workers": 0,
                    "comfy_online": False,
                    "error": f"Middleware returned {response.status_code}"
                }
    except Exception as e:
        logger.error(f"Error proxying system status: {e}")
        return {
            "queue_size": 0,
            "queue_by_type": {},
            "active_workers": 0,
            "comfy_online": False,
            "error": str(e)
        }

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
                raise HTTPException(status_code=response.status_code, detail="Task not found or error")
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

        return StreamingResponse(
            iter_file(),
            media_type=r.headers.get("content-type")
        )

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

        return StreamingResponse(
            iter_file(),
            media_type=r.headers.get("content-type")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying video: {e}")
        raise HTTPException(status_code=500, detail=str(e))
