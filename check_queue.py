import asyncio
import redis.asyncio as redis

REDIS_URL = "redis://:redispassword@127.0.0.1:6379/1"

async def main():
    r = redis.from_url(REDIS_URL)
    
    # Check queue lengths
    for q in ["comfy:queue:pending", "comfy:queue:priority"]:
        length = await r.llen(q)
        print(f"Queue '{q}' length: {length}")
        
    await r.close()

asyncio.run(main())
