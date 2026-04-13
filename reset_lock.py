import asyncio
from src.services.redis_client import redis_client

async def main():
    keys = await redis_client.redis.keys("*user_concurrency*")
    if keys:
        await redis_client.redis.delete(*keys)
    print("Lock reset.")

if __name__ == "__main__":
    asyncio.run(main())
