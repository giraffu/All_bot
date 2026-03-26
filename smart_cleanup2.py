import asyncio
import time
import json
import httpx
from src.database.core import init_db
from src.services.redis_client import redis_client
from src.services.permission_service import permission_service
from config import API_BASE

async def main():
    await init_db()
    tasks = await redis_client.get_active_tasks()
    if not tasks:
        print("No active tasks found.")
        return

    print(f"Found {len(tasks)} active tasks. Checking status...")
    
    removed = 0
    now = time.time()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for task_id, task in tasks.items():
            backend_task_id = task.get("backend_task_id")
            user_id = task.get("user_id")
            username = task.get("username", "Unknown")
            cost = task.get("cost", 0)
            age = now - task.get('created_at', now)
            
            is_dead = False
            
            if not backend_task_id:
                if age > 300: # 5 minutes without backend ID
                    is_dead = True
                    print(f"Task {task_id} (User: {username}, Age: {age:.1f}s) has no backend_task_id and is old. Marking as dead.")
                else:
                    print(f"Task {task_id} (User: {username}, Age: {age:.1f}s) has no backend_task_id but is new.")
            else:
                try:
                    resp = await client.get(f"{API_BASE}/status/{backend_task_id}")
                    print(f"Task {task_id} (User: {username}, Age: {age:.1f}s) Backend {backend_task_id} - HTTP {resp.status_code}")
                    if resp.status_code == 200:
                        status_data = resp.json()
                        state = status_data.get("status")
                        print(f" -> State: {state}")
                        if state in ["error", "unknown"] or not state:
                            is_dead = True
                            print(f" -> Marking as dead.")
                    elif resp.status_code == 404:
                        is_dead = True
                        print(f" -> Not found (404). Marking as dead.")
                except Exception as e:
                    print(f"Task {task_id} (User: {username}, Age: {age:.1f}s) Backend {backend_task_id} - ERROR: {e}")
                    if age > 600: # If we can't reach backend and task is older than 10 mins, assume dead
                        is_dead = True
                        print(f" -> Marking as dead due to age and error.")

            if is_dead:
                print(f"Refunding {cost} credits to user {user_id} and removing task {task_id}...")
                if cost > 0 and user_id:
                    try:
                        await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund_cleanup")
                        print(f"Refunded {cost} credits to {user_id}.")
                    except Exception as e:
                        print(f"Error refunding: {e}")
                
                # Remove from redis
                await redis_client.remove_active_task(task_id)
                if user_id:
                    await redis_client.decrement_user_concurrency(user_id)
                removed += 1
                
    print(f"Cleanup complete. Removed {removed} dead tasks.")

if __name__ == "__main__":
    asyncio.run(main())
