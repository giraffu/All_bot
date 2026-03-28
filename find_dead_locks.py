import asyncio
import time
import redis.asyncio as redis
import json
from config import REDIS_URL, REDIS_PREFIX

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Active tasks
    tasks_data = await r.hgetall(f"{REDIS_PREFIX}active_tasks")
    active_user_ids = set()
    for task_id, task_data_str in tasks_data.items():
        task = json.loads(task_data_str)
        active_user_ids.add(int(task.get('user_id')))

    # Concurrency locks
    keys = await r.keys(f"{REDIS_PREFIX}user_concurrency:*")
    dead_locks = []
    for key in keys:
        val = await r.get(key)
        if val and int(val) > 0:
            user_id = int(key.split(':')[-1])
            if user_id not in active_user_ids:
                dead_locks.append((user_id, val))

    print(f"--- Dead Concurrency Locks ({len(dead_locks)}) ---")
    for user_id, val in dead_locks:
        print(f"User ID: {user_id} | Concurrency: {val} (STUCK!)")
        # To fix: await r.set(key, 0)

    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
