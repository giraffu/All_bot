import asyncio
import json
import redis.asyncio as redis
from config import REDIS_URL

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    pending_tasks = await r.zrange("comfy:queue:pending", 0, -1)
    
    prod_bot_tasks_raw = await r.hgetall("prod_bot_active_tasks")
    prod_bot_tasks = {k: json.loads(v) for k, v in prod_bot_tasks_raw.items()}
    
    # In prod_bot_active_tasks, the key is usually the Bot's task_id (UUID), 
    # but the task dict might contain 'backend_task_id'. Let's check.
    backend_ids_in_bot = set()
    for bot_task_id, task_data in prod_bot_tasks.items():
        backend_id = task_data.get('backend_task_id')
        if backend_id:
            backend_ids_in_bot.add(backend_id)
            
    print(f"Total pending tasks in backend: {len(pending_tasks)}")
    print(f"Total active tasks in prod_bot: {len(prod_bot_tasks)}")
    
    pending_not_in_bot = [t for t in pending_tasks if t not in backend_ids_in_bot]
    print(f"Tasks in pending but NOT in prod_bot_active_tasks: {len(pending_not_in_bot)}")
    
    # Let's also check if these tasks are really "zombies" (e.g. no longer exist in any bot active tasks)
    test_bot_tasks_raw = await r.hgetall("test_bot_active_tasks")
    test_bot_tasks = {k: json.loads(v) for k, v in test_bot_tasks_raw.items()}
    for bot_task_id, task_data in test_bot_tasks.items():
        backend_id = task_data.get('backend_task_id')
        if backend_id:
            backend_ids_in_bot.add(backend_id)
            
    pending_not_in_any_bot = [t for t in pending_tasks if t not in backend_ids_in_bot]
    print(f"Tasks in pending but NOT in ANY bot active tasks: {len(pending_not_in_any_bot)}")
    
    await r.aclose()

asyncio.run(main())
