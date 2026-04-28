import asyncio
import redis.asyncio as redis

REDIS_URL = "redis://:redispassword@127.0.0.1:6379/1"

async def main():
    user_id = 1331356067
    
    r = redis.from_url(REDIS_URL)
    
    # Check concurrency lock
    lock_key = f"allbot:user_concurrency:{user_id}"
    lock_val = await r.get(lock_key)
    
    print(f"Concurrency lock for user {user_id}: {lock_val}")
    
    # Let's also check active tasks or queues if we know their names
    # E.g. allbot:user_concurrency:* to see how many locks are there
    keys = await r.keys("allbot:user_concurrency:*")
    print(f"Total concurrency locks in Redis: {len(keys)}")
    
    await r.close()

asyncio.run(main())
