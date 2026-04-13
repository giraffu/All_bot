import asyncio
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    task_info = await r.hgetall(f"comfy:task:f92c2204-2f2f-428c-b630-b113dad19de2")
    print(f"Task error: {task_info.get('error_msg')}")

if __name__ == "__main__":
    asyncio.run(main())
