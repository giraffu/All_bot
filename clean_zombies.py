import asyncio
import time
import redis.asyncio as redis
import json
import httpx
from config import REDIS_URL, REDIS_PREFIX, API_BASE, API_TOKEN

async def cancel_backend_task(task_id: str):
    url = f"{API_BASE}/api/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers, timeout=5.0)
            if response.status_code in [200, 404]:
                print(f"Backend cancelled task {task_id}: {response.status_code}")
            else:
                print(f"Failed to cancel backend task {task_id}: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error cancelling backend task {task_id}: {e}")

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
            backend_task_id = task.get('backend_task_id')
            print(f"Removing zombie task: {task_id} (User: {task.get('username')}, Age: {age:.1f}s)")
            
            # Delete from Redis
            await r.hdel(f"{REDIS_PREFIX}active_tasks", task_id)
            
            if user_id:
                # Decrement concurrency to prevent user lockout
                key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
                val = await r.decr(key)
                if val < 0:
                    await r.set(key, 0)
            
            # Notify backend to cancel the task and save resources
            if backend_task_id:
                await cancel_backend_task(backend_task_id)
            elif task_id:
                # Sometimes bot task_id is same as backend_task_id depending on how it was stored
                await cancel_backend_task(task_id)
                
            removed += 1
            
    print(f"Removed {removed} zombie tasks.")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
