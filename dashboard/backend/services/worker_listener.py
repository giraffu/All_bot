import asyncio
import json
import logging
import os
from datetime import datetime

import redis.asyncio as redis
from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import WorkerLog

logger = logging.getLogger("dashboard.worker_listener")


def _build_task_info_from_event(event_data):
    task_type = event_data.get("task_type") or event_data.get("type")
    worker_id = event_data.get("worker_id")
    created_at = event_data.get("created_at")

    if not any(value not in (None, "") for value in (task_type, worker_id, created_at)):
        return None

    return {
        "worker_id": worker_id or "unknown",
        "type": task_type or "unknown",
        "created_at": created_at,
    }


async def start_worker_listener(task_registry: set | None = None):
    """Background task to listen for ComfyUI task events and record worker logs."""
    restart_delay_seconds = int(os.getenv("WORKER_LISTENER_RESTART_DELAY", "5"))
    while True:
        try:
            await _run_worker_listener_once(task_registry=task_registry)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                "!!! [WORKER_LISTENER] Worker listener crashed: %s",
                e,
                exc_info=True,
            )
            await asyncio.sleep(restart_delay_seconds)


async def _close_redis_resource(resource) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if asyncio.iscoroutine(result):
        await result


async def _run_worker_listener_once(task_registry: set | None = None):
    logger.info("Starting Worker Task Listener...")
    redis_url_worker = os.getenv("WORKER_REDIS_URL", "redis://redis:6379/2")
    r_worker = redis.from_url(redis_url_worker, decode_responses=True)

    redis_url_bot = os.getenv("REDIS_URL", "redis://redis:6379/1")
    r_bot = redis.from_url(redis_url_bot, decode_responses=True)

    pubsub = r_worker.pubsub()
    background_tasks = set()
    try:
        await pubsub.psubscribe("comfy:task_events:*")
        logger.info("Subscribed to comfy:task_events:*")

        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                task = asyncio.create_task(process_message(message, r_worker, r_bot))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
    finally:
        for task in list(background_tasks):
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        await _close_redis_resource(pubsub)
        await _close_redis_resource(r_worker)
        await _close_redis_resource(r_bot)


async def resolve_task_info(task_id: str, event_data: dict, r_worker, r_bot) -> dict:
    task_info = _build_task_info_from_event(event_data) or {}
    task_key = f"comfy:task:{task_id}"
    if not task_info:
        task_info = await r_worker.hgetall(task_key)

    if not task_info:
        task_info = await r_worker.hgetall(task_id)

    if not task_info:
        active_tasks_key = f"{os.getenv('REDIS_PREFIX', 'prod_bot_')}active_tasks"
        active_tasks_str = await r_bot.hget(active_tasks_key, task_id)
        if active_tasks_str:
            try:
                bot_task_data = json.loads(active_tasks_str)
                task_info = {
                    "worker_id": "unknown",
                    "type": bot_task_data.get("task_type", "unknown"),
                    "created_at": bot_task_data.get("created_at"),
                }
            except Exception as e:
                logger.error("Error parsing bot task data: %s", e)

    if not task_info:
        task_info = await r_bot.hgetall(task_key)
        if not task_info:
            task_info = await r_bot.hgetall(task_id)

    if task_info:
        return task_info

    logger.warning("Task %s completed/failed but no details found in Redis.", task_id)
    return {
        "worker_id": "unknown",
        "type": "unknown",
        "created_at": datetime.now().timestamp(),
    }


def build_worker_log(task_id: str, event_data: dict, task_info: dict) -> WorkerLog:
    worker_id = task_info.get("worker_id", "unknown")
    task_type = task_info.get("type", "unknown")
    created_at_val = task_info.get("created_at")
    if created_at_val:
        try:
            created_at_ts = float(created_at_val)
        except ValueError:
            created_at_ts = None
    else:
        created_at_ts = None

    start_time = datetime.fromtimestamp(created_at_ts) if created_at_ts else datetime.now()
    end_time = datetime.now()
    duration = int((end_time - start_time).total_seconds())
    error_msg = event_data.get("error_msg", "") or task_info.get("error_msg", "")
    final_status = "success" if event_data.get("status") == "done" else "failed"

    return WorkerLog(
        worker_id=worker_id,
        task_id=task_id,
        task_type=task_type,
        status=final_status,
        start_time=start_time,
        end_time=end_time,
        duration=duration,
        error_message=str(error_msg),
    )


async def persist_worker_log_once(log_entry: WorkerLog) -> bool:
    try:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(WorkerLog).where(WorkerLog.task_id == log_entry.task_id)
            )
            if existing.scalars().first():
                return False
            session.add(log_entry)
            try:
                await session.commit()
                logger.info(
                    "Recorded worker log for task %s by %s (%s)",
                    log_entry.task_id,
                    log_entry.worker_id,
                    log_entry.status,
                )
                return True
            except Exception:
                return False
    except Exception as inner_e:
        logger.error(
            "!!! [WORKER_LISTENER] Inner error: %s",
            inner_e,
            exc_info=True,
        )
        return False


async def process_message(message, r_worker, r_bot):
    try:
        channel = message["channel"]
        task_id = channel.split(":")[-1]
        data = message["data"]

        event_data = json.loads(data)
        status = event_data.get("status")

        if status in ["done", "error"]:
            lock_key = f"worker_listener:lock:{task_id}:{status}"
            acquired = await r_worker.set(lock_key, "1", ex=3600, nx=True)
            if not acquired:
                return

            logger.info(
                "Saving log for task_id=%s status=%s",
                task_id,
                status,
            )
            task_info = await resolve_task_info(task_id, event_data, r_worker, r_bot)
            await persist_worker_log_once(build_worker_log(task_id, event_data, task_info))

    except json.JSONDecodeError:
        logger.error(
            "!!! [WORKER_LISTENER] Failed to parse event data: %s",
            message.get("data"),
        )
    except Exception:
        logger.exception("!!! [WORKER_LISTENER] Error processing task event")
