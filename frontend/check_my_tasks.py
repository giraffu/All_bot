import asyncio
from redis.asyncio import Redis

async def main():
    r = Redis.from_url("redis://:redispassword@127.0.0.1:6379/2", decode_responses=True)
    task1 = "f92c2204-2f2f-428c-b630-b113dad19de2"
    task2 = "cc9ad78a-5910-4bda-9fba-8c16f71dc98f"
    for task_id in [task1, task2]:
        rank = await r.zrank("comfy:queue:pending", task_id)
        task_info = await r.hgetall(f"comfy:task:{task_id}")
        print(f"Task {task_id}: rank={rank}, status={task_info.get('status')}, type={task_info.get('type')}, priority={task_info.get('priority')}")

if __name__ == "__main__":
    asyncio.run(main())
