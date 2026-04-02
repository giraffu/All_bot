import asyncio
import redis.asyncio as redis
from config import REDIS_URL

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    pending_count = await r.zcard("comfy:queue:pending")
    
    prod_bot_tasks = await r.hgetall("prod_bot_active_tasks")
    test_bot_tasks = await r.hgetall("test_bot_active_tasks")
    bot_tasks = await r.hgetall("bot_active_tasks")
    
    print(f"comfy:queue:pending: {pending_count}")
    print(f"prod_bot_active_tasks: {len(prod_bot_tasks)}")
    print(f"test_bot_active_tasks: {len(test_bot_tasks)}")
    print(f"bot_active_tasks: {len(bot_tasks)}")
    await r.aclose()

asyncio.run(main())
