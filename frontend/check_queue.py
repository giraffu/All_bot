import asyncio
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    items = await r.zrange("comfy:queue:pending", 0, 5, withscores=True)
    print("Top 6 tasks in queue:")
    for i, (task_id, score) in enumerate(items):
        task_info = await r.hgetall(f"comfy:task:{task_id}")
        print(f"{i}. {task_id} (score {score}) - Type: {task_info.get('type')}, Priority: {task_info.get('priority')}")

if __name__ == "__main__":
    asyncio.run(main())
