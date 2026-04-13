import asyncio
import json
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    keys = await r.keys("comfy:task:*")
    tasks = []
    for k in keys:
        task_info = await r.hgetall(k)
        if task_info.get("status") == "done":
            tasks.append((k, task_info))
    tasks.sort(key=lambda x: x[1].get('created_at', ''), reverse=True)
    if tasks:
        print(f"Latest task: {tasks[0][0]}")
        print(json.dumps(tasks[0][1], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
