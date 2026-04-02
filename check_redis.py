import asyncio
import time
import redis.asyncio as redis
import json
from config import REDIS_URL, REDIS_PREFIX

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Active tasks
    tasks = await r.hgetall(f"{REDIS_PREFIX}active_tasks")
    print(f"--- Active Tasks ({len(tasks)}) ---")
    now = time.time()
    for task_id, task_data_str in tasks.items():
        task = json.loads(task_data_str)
        age = now - task.get('created_at', now)
        print(f"User: {task.get('username')} ({task.get('user_id')}) | Age: {age:.1f}s | Type: {task.get('task_type')}")

    # Concurrency locks
    keys = await r.keys(f"{REDIS_PREFIX}user_concurrency:*")
    print(f"\n--- Concurrency Locks ({len(keys)}) ---")
    for key in keys:
        val = await r.get(key)
        if val and int(val) > 0:
            user_id = key.split(':')[-1]
            # Check if this user has active tasks
            has_task = any(json.loads(t).get('user_id') == int(user_id) for t in tasks.values())
            print(f"User ID: {user_id} | Concurrency: {val} | Has Active Task: {has_task}")

    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
