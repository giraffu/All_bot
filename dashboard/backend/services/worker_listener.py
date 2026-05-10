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


async def start_worker_listener():
    """Background task to listen for ComfyUI task events and record worker logs."""
    try:
        logger.info("Starting Worker Task Listener...")
        # Connect to Redis
        redis_url_worker = os.getenv("WORKER_REDIS_URL", "redis://redis:6379/2")
        r_worker = redis.from_url(redis_url_worker, decode_responses=True)

        redis_url_bot = os.getenv("REDIS_URL", "redis://redis:6379/1")
        r_bot = redis.from_url(redis_url_bot, decode_responses=True)

        pubsub = r_worker.pubsub()
        await pubsub.psubscribe("comfy:task_events:*")

        logger.info("Subscribed to comfy:task_events:*")

        background_tasks = set()

        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                # Do not block the pubsub listener loop
                task = asyncio.create_task(process_message(message, r_worker, r_bot))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)

    except Exception as e:
        logger.error(
            f"!!! [WORKER_LISTENER] Worker listener crashed: {e}", exc_info=True
        )
        # Retry logic could be added here
        await asyncio.sleep(5)
        task = asyncio.create_task(start_worker_listener())
        from dashboard.backend.main import background_tasks

        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


async def process_message(message, r_worker, r_bot):
    try:
        channel = message["channel"]
        task_id = channel.split(":")[-1]
        data = message["data"]

        event_data = json.loads(data)
        status = event_data.get("status")

        if status in ["done", "error"]:
            # Prevent duplicate processing using Redis lock
            lock_key = f"worker_listener:lock:{task_id}:{status}"
            acquired = await r_worker.set(lock_key, "1", ex=3600, nx=True)
            if not acquired:
                return

            # 1. Fetch from worker DB
            task_key = f"comfy:task:{task_id}"
            task_info = await r_worker.hgetall(task_key)

            # 2. Try another pattern in worker DB just in case
            if not task_info:
                task_info = await r_worker.hgetall(task_id)

            # 3. If not found, fetch from bot DB active tasks
            if not task_info:
                active_tasks_key = (
                    f"{os.getenv('REDIS_PREFIX', 'prod_bot_')}active_tasks"
                )
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
                        logger.error(f"Error parsing bot task data: {e}")

            # 4. Try from DB 1 direct key
            if not task_info:
                task_info = await r_bot.hgetall(task_key)
                if not task_info:
                    task_info = await r_bot.hgetall(task_id)

            if not task_info:
                logger.warning(
                    f"Task {task_id} completed/failed but no details found in Redis."
                )
                # Fallback to default structure so we don't drop the log
                task_info = {
                    "worker_id": "unknown",
                    "type": "unknown",
                    "created_at": datetime.now().timestamp(),
                }

            worker_id = task_info.get("worker_id", "unknown")
            task_type = task_info.get("type", "unknown")

            # Safe float conversion
            created_at_val = task_info.get("created_at")
            if created_at_val:
                try:
                    created_at_ts = float(created_at_val)
                except ValueError:
                    created_at_ts = None
            else:
                created_at_ts = None

            start_time = (
                datetime.fromtimestamp(created_at_ts)
                if created_at_ts
                else datetime.now()
            )
            end_time = datetime.now()
            duration = int((end_time - start_time).total_seconds())

            error_msg = event_data.get("error_msg", "") or task_info.get(
                "error_msg", ""
            )
            final_status = "success" if status == "done" else "failed"

            logger.info(
                f"Saving log: worker_id={worker_id}, task_id={task_id}, type={task_type}"
            )

            # Save to database
            try:
                async with AsyncSessionLocal() as session:
                    # Check if already exists to prevent duplicate logs from multiple gunicorn workers
                    existing = await session.execute(
                        select(WorkerLog).where(WorkerLog.task_id == task_id)
                    )
                    if not existing.scalars().first():
                        log_entry = WorkerLog(
                            worker_id=worker_id,
                            task_id=task_id,
                            task_type=task_type,
                            status=final_status,
                            start_time=start_time,
                            end_time=end_time,
                            duration=duration,
                            error_message=str(error_msg),
                        )
                        session.add(log_entry)
                        try:
                            await session.commit()
                            logger.info(
                                f"Recorded worker log for task {task_id} by {worker_id} ({final_status})"
                            )
                        except Exception as e:
                            # Might be IntegrityError if multiple workers try to insert simultaneously
                            pass
            except Exception as inner_e:
                logger.error(
                    f"!!! [WORKER_LISTENER] Inner error: {inner_e}", exc_info=True
                )

    except json.JSONDecodeError:
        print(
            f"!!! [WORKER_LISTENER] Failed to parse event data: {message.get('data')}"
        )
    except Exception as e:
        print(f"!!! [WORKER_LISTENER] Error processing task event: {e}")
