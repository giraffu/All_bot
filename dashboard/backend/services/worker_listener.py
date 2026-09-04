import asyncio
import json
import logging
import os
from datetime import datetime

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import WorkerLog
from src.services.redis_connection import build_redis_client

from dashboard.backend.services.worker_gpu_telemetry import (
    GPU_PHASE_TTL_SECONDS,
    build_gpu_phase_marker,
    gpu_phase_key,
    resolve_worker_gpu_equivalence,
)

logger = logging.getLogger("dashboard.worker_listener")


def _now_timestamp() -> float:
    return datetime.now().timestamp()


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
    poll_timeout_seconds = float(os.getenv("WORKER_LISTENER_POLL_TIMEOUT", "30"))
    redis_url_worker = os.getenv("WORKER_REDIS_URL", "redis://redis:6379/2")
    r_worker = build_redis_client(redis_url_worker, decode_responses=True)

    redis_url_bot = os.getenv("REDIS_URL", "redis://redis:6379/1")
    r_bot = build_redis_client(redis_url_bot, decode_responses=True)

    pubsub = r_worker.pubsub()
    background_tasks = set()
    try:
        await pubsub.psubscribe("comfy:task_events:*")
        logger.info("Subscribed to comfy:task_events:*")

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=poll_timeout_seconds,
            )
            if message is None:
                continue
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


def build_worker_log(
    task_id: str,
    event_data: dict,
    task_info: dict,
    *,
    gpu_phase: dict | None = None,
) -> WorkerLog:
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

    started_at = None
    finished_at = None
    if gpu_phase:
        try:
            started_at = float(gpu_phase.get("started_at"))
            finished_at = float(gpu_phase.get("finished_at"))
        except (TypeError, ValueError):
            started_at = None
            finished_at = None

    has_exact_gpu_phase = bool(
        started_at is not None and finished_at is not None and finished_at >= started_at
    )
    if has_exact_gpu_phase:
        start_time = datetime.fromtimestamp(started_at)
        end_time = datetime.fromtimestamp(finished_at)
        duration = max(1, round(finished_at - started_at))
    else:
        start_time = (
            datetime.fromtimestamp(created_at_ts) if created_at_ts else datetime.now()
        )
        end_time = datetime.now()
        duration = max(0, int((end_time - start_time).total_seconds()))
    error_msg = event_data.get("error_msg", "") or task_info.get("error_msg", "")
    final_status = "success" if event_data.get("status") == "done" else "failed"
    if final_status == "success" and has_exact_gpu_phase:
        equivalence = resolve_worker_gpu_equivalence(worker_id)
        if equivalence is not None:
            error_msg = build_gpu_phase_marker(equivalence)

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
        execution_phase = event_data.get("execution_phase")

        if status == "running" and execution_phase in {
            "running",
            "gpu_done",
            "delivering",
        }:
            phase_key = gpu_phase_key(task_id)
            field = "started_at" if execution_phase == "running" else "finished_at"
            await r_worker.hsetnx(phase_key, field, str(_now_timestamp()))
            await r_worker.expire(phase_key, GPU_PHASE_TTL_SECONDS)
            return

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
            phase_key = gpu_phase_key(task_id)
            gpu_phase = await r_worker.hgetall(phase_key)
            persisted = await persist_worker_log_once(
                build_worker_log(
                    task_id,
                    event_data,
                    task_info,
                    gpu_phase=gpu_phase,
                )
            )
            if persisted:
                await r_worker.delete(phase_key)

    except json.JSONDecodeError:
        logger.error(
            "!!! [WORKER_LISTENER] Failed to parse event data: %s",
            message.get("data"),
        )
    except Exception:
        logger.exception("!!! [WORKER_LISTENER] Error processing task event")
