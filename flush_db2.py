import asyncio
import redis.asyncio as redis

async def main():
    r = redis.from_url('redis://:redispassword@host.docker.internal:6379/2')
    print("Flushing DB2...")
    await r.flushdb()
    print("Done")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
