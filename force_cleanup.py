import asyncio
import time
from src.database.core import init_db
from src.services.redis_client import redis_client
from src.services.permission_service import permission_service

async def main():
    await init_db()
    tasks = await redis_client.get_active_tasks()
    if not tasks:
        print("No active tasks found.")
        return

    print(f"Found {len(tasks)} active tasks. Force cleaning tasks older than 10 minutes...")
    
    removed = 0
    now = time.time()
    
    for task_id, task in tasks.items():
        user_id = task.get("user_id")
        username = task.get("username", "Unknown")
        cost = task.get("cost", 0)
        age = now - task.get('created_at', now)
        
        # 强制清理大于 7200 秒 (2小时) 的任务
        if age > 7200:
            print(f"Removing stuck task {task_id} (User: {username}, Age: {age:.1f}s)...")
            
            if cost > 0 and user_id:
                try:
                    await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund_stuck_task")
                    print(f" -> Refunded {cost} credits to {user_id}.")
                except Exception as e:
                    print(f" -> Error refunding: {e}")
            
            # Remove from redis
            await redis_client.remove_active_task(task_id)
            if user_id:
                await redis_client.decrement_user_concurrency(user_id)
            removed += 1
                
    print(f"Cleanup complete. Force removed {removed} stuck tasks.")

if __name__ == "__main__":
    asyncio.run(main())
