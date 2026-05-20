import asyncio
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    process_and_submit_task,
)
from src.constants import VIDEO_TASK_TYPES
from src.core.media_paths import resolve_storage_object
from src.database.models import User, History
from src.quota import QuotaManager
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.services.image_service import image_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.web_api.dependencies import get_current_user, get_current_user_once, get_db
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse, TaskResultResponse

router = APIRouter()
logger = logging.getLogger(__name__)
quota_manager = QuotaManager()


def _build_terminal_progress_payload(status_data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    payload = dict(status_data)
    status_val = payload.get("status")

    if status_val == "done":
        payload["status"] = "success"
        payload["task_id"] = task_id
        payload["task_type"] = payload.get("task_type", "edit")
        return payload

    if status_val == "error":
        payload["status"] = "failed"
        payload["task_id"] = task_id
        payload["error"] = payload.get("error_msg")
        payload.pop("error_msg", None)
        return payload

    if status_val == "cancelled":
        payload["status"] = "failed"
        payload["task_id"] = task_id
        payload["error"] = payload.get("error_msg") or "任务已取消"
        payload.pop("error_msg", None)
        return payload

    return None


async def _get_user_history_record(task_id: str, user_id: int, session_factory) -> History | None:
    async with session_factory() as session:
        result = await session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == user_id,
            )
        )
        return result.scalars().first()


async def _get_owned_active_task(task_id: str, user_id: int) -> dict[str, Any] | None:
    tasks = await redis_client.get_active_tasks()
    task = tasks.get(task_id)
    if task and task.get("user_id") == user_id:
        return task
    return None


async def _build_not_found_progress_payload(task_id: str, user_id: int, session_factory) -> dict[str, Any]:
    history = await _get_user_history_record(task_id, user_id, session_factory)
    if history:
        return {
            "status": "success",
            "task_id": task_id,
            "task_type": history.type or "edit",
        }

    return {
        "status": "failed",
        "task_id": task_id,
        "error": "任务不存在或无权限",
    }


@router.delete("/cancel/{task_id}")
async def cancel_pending_task(task_id: str, current_user: User = Depends(get_current_user)):
    try:
        from src.core.task_core import cancel_user_task
        result = await cancel_user_task(task_id, current_user.id)
        return {
            "status": "success",
            "message": result.get("message", "取消请求已受理"),
            "cancel_state": result.get("state"),
        }
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/generate", response_model=TaskGenerateResponse)
async def create_generation_task(
    req: TaskGenerateRequest, current_user: User = Depends(get_current_user)
):
    """
    Submit a generation task (image/video).
    """
    try:
        is_template = getattr(req, "is_template", False)

        # Merge prompt from request into inputs if it exists, so core layer can use it
        if req.prompt:
            req.inputs["prompt"] = req.prompt

        import uuid

        task_id = str(uuid.uuid4())

        from asgi_correlation_id import correlation_id

        correlation_id.set(task_id)

        result = await process_and_submit_task(
            user_id=current_user.id,
            username=current_user.username,
            task_type=req.task_type,
            inputs=req.inputs,
            task_id=task_id,
            base_priority=req.priority,
            is_template=is_template,
            source_post_id=req.source_post_id,
        )

        balance = await quota_manager.get_credits(current_user.id)
        return TaskGenerateResponse(
            task_id=result["task_id"],
            status="pending",
            message="Task submitted successfully",
            cost=result["cost"],
            balance_remaining=balance,
        )
    except ConcurrencyLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except InsufficientCreditsError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except CoreDomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Task submission error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{task_id}/result", response_model=TaskResultResponse)
async def get_task_result(
    task_id: str, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get task generation result directly.
    """

    hist = (
        (
            await db.execute(
                select(History).where(
                    History.task_id == task_id,
                    History.user_id == current_user.id,
                )
            )
        )
        .scalars()
        .first()
    )

    if not hist:
        return {
            "status": "pending_result",
            "task_id": task_id,
            "task_type": None,
            "media_type": None,
        }

    is_video = hist.type in VIDEO_TASK_TYPES if hist.type else False
    media_type = "video" if is_video else "image"

    if hist.output_file:
        bucket_name, object_name = resolve_storage_object(hist.output_file)
        presigned_url = storage.get_presigned_url(
            object_name, expires_hours=24, bucket=bucket_name
        )
        return {
            "status": "success",
            "task_id": task_id,
            "task_type": hist.type,
            "media_type": media_type,
            "result_url": presigned_url if presigned_url else hist.output_file,
        }
    else:
        return {
            "status": "pending_result",
            "task_id": task_id,
            "task_type": hist.type,
            "media_type": media_type,
        }


@router.get("/{task_id}/stream")
async def task_status_stream(
    task_id: str,
    current_user: User = Depends(get_current_user_once),
):
    """
    SSE Endpoint for real-time task progress tracking.
    Listens to Redis Pub/Sub channel: comfy:task_events:{task_id}
    Also periodically sends queue position while pending.
    """
    from config import API_BASE
    from src.database.core import AsyncSessionLocal
    user_id = current_user.id

    owned_active_task = await _get_owned_active_task(task_id, user_id)
    owned_history = await _get_user_history_record(task_id, user_id, AsyncSessionLocal)
    if not owned_active_task and not owned_history:
        raise HTTPException(status_code=404, detail="任务不存在或无权限")

    async def get_task_status_full():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/status/{task_id}", timeout=2.0)
                if resp.status_code == 404:
                    return {"not_found": True}
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "Unexpected status while getting task %s state: %s",
                task_id,
                e.response.status_code,
            )
        except Exception as e:
            logger.error(f"Error getting status for {task_id}: {e}")
        return None

    async def event_generator():
        pubsub = redis_client.redis.pubsub()
        channel = f"comfy:task_events:{task_id}"
        await pubsub.subscribe(channel)

        try:
            # Initial connection message
            yield {
                "event": "connected",
                "data": json.dumps({"status": "listening", "task_id": task_id}),
            }

            # Fetch initial status to avoid missing early completion/error events
            initial_status = await get_task_status_full()
            is_running = False

            if initial_status:
                if initial_status.get("not_found"):
                    yield {
                        "event": "progress",
                        "data": json.dumps(
                            await _build_not_found_progress_payload(
                                task_id,
                                user_id,
                                AsyncSessionLocal,
                            )
                        ),
                    }
                    return

                status_val = initial_status.get("status")
                if status_val == "running":
                    is_running = True
                else:
                    terminal_payload = _build_terminal_progress_payload(initial_status, task_id)
                    if terminal_payload:
                        yield {"event": "progress", "data": json.dumps(terminal_payload)}
                        return  # End stream immediately

            last_queue_check = 0

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Parse to see if finished or running
                    try:
                        parsed = json.loads(data)
                        task_status = parsed.get("status")

                        terminal_payload = _build_terminal_progress_payload(parsed, task_id)
                        if terminal_payload:
                            parsed = terminal_payload

                        # Yield the mapped data
                        yield {"event": "progress", "data": json.dumps(parsed)}

                        if task_status == "running":
                            is_running = True
                        elif task_status in ["done", "error", "cancelled"]:
                            # End stream gracefully
                            break
                    except json.JSONDecodeError:
                        yield {"event": "progress", "data": data}

                # Periodically send queue position if not running yet
                if not is_running:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_check > 5.0:  # Check every 5 seconds
                        status_data = await get_task_status_full()
                        if status_data:
                            if status_data.get("not_found"):
                                yield {
                                    "event": "progress",
                                    "data": json.dumps(
                                        await _build_not_found_progress_payload(
                                            task_id,
                                            user_id,
                                            AsyncSessionLocal,
                                        )
                                    ),
                                }
                                break

                            status_val = status_data.get("status")
                            # If the task actually started or finished but we missed the pubsub message
                            if status_val == "running":
                                is_running = True
                            else:
                                terminal_payload = _build_terminal_progress_payload(status_data, task_id)
                                if terminal_payload:
                                    yield {
                                        "event": "progress",
                                        "data": json.dumps(terminal_payload),
                                    }
                                    break

                                queue_pos = status_data.get("queue_pos")
                                if queue_pos is not None:
                                    yield {
                                        "event": "progress",
                                        "data": json.dumps(
                                            {"status": "pending", "queue_pos": queue_pos}
                                        ),
                                    }
                        last_queue_check = current_time

                # Check if client disconnected
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected for task {task_id}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())


@router.get("/queue-status")
async def get_queue_status(_current_user: User = Depends(get_current_user)) -> dict:
    """获取当前系统的排队宏观大盘数据"""
    status = await image_service.get_queue_info()
    if not status:
        return {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}
    return status
