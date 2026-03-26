import asyncio
import time
import redis.asyncio as redis
import json

async def main():
    r = redis.from_url("redis://:redispassword@127.0.0.1:6379/0", decode_responses=True)
    
    tasks = await r.hgetall("prod_bot_active_tasks")
    now = time.time()
    removed = 0
    for task_id, task_data_str in tasks.items():
        task = json.loads(task_data_str)
        age = now - task.get('created_at', now)
        if age > 7200: # Older than 2 hours
            print(f"Removing zombie task: {task_id} (User: {task.get('username')}, Age: {age:.1f}s)")
            await r.hdel("prod_bot_active_tasks", task_id)
            removed += 1
            
    print(f"Removed {removed} zombie tasks.")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
