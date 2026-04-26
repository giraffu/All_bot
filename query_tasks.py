import asyncio
from redis import asyncio as aioredis
import json
from datetime import datetime, timedelta

async def main():
    try:
        redis = await aioredis.from_url('redis://:redispassword@127.0.0.1:6379/0', decode_responses=True)
        
        task_keys = await redis.keys('comfy:task:*')
        print(f"Found {len(task_keys)} tasks in Redis.")
        
        failed_tasks = []
        for key in task_keys:
            try:
                task_data_str = await redis.get(key)
                if task_data_str:
                    task = json.loads(task_data_str)
                    if task.get('status') in ['failed', 'error']:
                        failed_tasks.append(task)
            except Exception as e:
                pass
                    
        print(f"Found {len(failed_tasks)} failed tasks in Redis.")
        if failed_tasks:
            print("Sample failed task:", failed_tasks[0])
            
        await redis.close()
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    asyncio.run(main())
