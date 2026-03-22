import asyncio
from src.services.redis_client import redis_client
from src.api_client import image_service

async def check():
    tasks = await redis_client.get_active_tasks()
    print(f"Total active tasks in Redis: {len(tasks)}")
    for tid, task in tasks.items():
        print(f"Task ID: {tid}, Backend Task ID: {task.get('backend_task_id')}, User: {task.get('user_id')}")

if __name__ == "__main__":
    asyncio.run(check())
