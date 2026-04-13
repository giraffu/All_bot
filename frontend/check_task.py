import asyncio
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    task_info = await r.hgetall(f"comfy:task:fde31d90-5245-4314-a9ca-ef12a89de8e4")
    print(f"Task: priority={task_info.get('priority')}, created_at={task_info.get('created_at')}")

if __name__ == "__main__":
    asyncio.run(main())
