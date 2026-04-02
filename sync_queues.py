import asyncio
import json
import redis.asyncio as redis
import os

# Using correct password
REDIS_URL = "redis://:redispassword@127.0.0.1:6379/0"
# Based on actual config file in the bot
REDIS_PREFIX = "bot_" 

async def main():
    print("Connecting to Redis...")
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Let's actually scan for the active_tasks key to be 100% sure
    keys = await r.keys("*active_tasks")
    print(f"Found active_tasks keys: {keys}")
    
    if not keys:
        print("No active_tasks keys found. Cannot proceed.")
        await r.aclose()
        return
        
    actual_key = keys[0]
    for k in keys:
        if "test_" not in k and "comfyui_" not in k:
            actual_key = k
            break
            
    print(f"Using key: {actual_key}")
    
    # 1. Fetch valid tasks from Bot
    print(f"Fetching active tasks from Bot ({actual_key})...")
    bot_active_tasks = await r.hgetall(actual_key)
    
    valid_backend_ids = set()
    for task_id, data_str in bot_active_tasks.items():
        try:
            data = json.loads(data_str)
            if 'backend_task_id' in data:
                valid_backend_ids.add(data['backend_task_id'])
        except json.JSONDecodeError:
            continue
            
    print(f"Found {len(valid_backend_ids)} valid active tasks in Bot out of {len(bot_active_tasks)} records.")
    
    # 2. Check API pending queue
    print("\nFetching API pending queue...")
    pending_tasks = await r.zrange("comfy:queue:pending", 0, -1)
    
    removed_count = 0
    for task_id in pending_tasks:
        if task_id not in valid_backend_ids:
            # Remove from pending queue
            await r.zrem("comfy:queue:pending", task_id)
            # Delete task hash
            await r.delete(f"comfy:task:{task_id}")
            removed_count += 1
            
    print(f"Removed {removed_count} abandoned tasks from API pending queue.")
    
    # 3. Clean up stuck running tasks in API
    print("\nChecking API running tasks...")
    running_tasks = await r.smembers("comfy:queue:running")
    
    stuck_removed = 0
    for task_id in running_tasks:
        if task_id not in valid_backend_ids:
            # Remove from running set
            await r.srem("comfy:queue:running", task_id)
            # Delete task hash
            await r.delete(f"comfy:task:{task_id}")
            stuck_removed += 1
            
    print(f"Removed {stuck_removed} abandoned tasks from API running set.")
    
    # 4. Final status
    final_pending = await r.zcard("comfy:queue:pending")
    final_running = await r.scard("comfy:queue:running")
    print(f"\nFinal API Queue Status:")
    print(f"Pending: {final_pending}")
    print(f"Running: {final_running}")

    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
