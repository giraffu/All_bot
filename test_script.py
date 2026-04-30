import asyncio
from config import REDIS_PREFIX
from src.services.redis_client import redis_client

async def main():
    print(f"Prefix is {REDIS_PREFIX}")
    count = await redis_client.redis.hlen(f"{REDIS_PREFIX}active_tasks")
    print(f"Count is {count}")

asyncio.run(main())
