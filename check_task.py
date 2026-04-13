import asyncio
import json
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    task_info = await r.hgetall("comfy:task:1d98d190-e1d5-4868-ae50-22b4aebe3db3")
    print(json.dumps(task_info, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
