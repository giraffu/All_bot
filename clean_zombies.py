import asyncio
import time
import redis.asyncio as redis
import json
from config import REDIS_URL, REDIS_PREFIX

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    tasks = await r.hgetall(f"{REDIS_PREFIX}active_tasks")
    now = time.time()
    removed = 0
    for task_id, task_data_str in tasks.items():
        task = json.loads(task_data_str)
        age = now - task.get('created_at', now)
        if age > 7200: # Older than 2 hours
            user_id = task.get('user_id')
            print(f"Removing zombie task: {task_id} (User: {task.get('username')}, Age: {age:.1f}s)")
            await r.hdel(f"{REDIS_PREFIX}active_tasks", task_id)
            if user_id:
                # Decrement concurrency to prevent user lockout
                key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
                val = await r.decr(key)
                if val < 0:
                    await r.set(key, 0)
            removed += 1
            
    print(f"Removed {removed} zombie tasks.")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
