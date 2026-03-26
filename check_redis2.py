import asyncio
import time
import redis.asyncio as redis
import json
import os
from config import REDIS_URL, REDIS_PREFIX

async def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Concurrency locks
    keys = await r.keys(f"{REDIS_PREFIX}user_concurrency:*")
    count = 0
    for key in keys:
        val = await r.get(key)
        if val and int(val) > 0:
            print(f"Key: {key}, Val: {val}")
            count += 1
    print(f"Total non-zero locks: {count}")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
