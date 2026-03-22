import json
import logging
from typing import Optional, Dict, Any
import redis.asyncio as redis
from config import REDIS_URL, REDIS_PREFIX

logger = logging.getLogger(__name__)

class RedisClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance.redis = redis.from_url(REDIS_URL, decode_responses=True)
        return cls._instance

    async def get_active_tasks(self) -> Dict[str, Any]:
        """获取所有运行中的任务"""
        key = f"{REDIS_PREFIX}active_tasks"
        try:
            tasks_raw = await self.redis.hgetall(key)
            return {k: json.loads(v) for k, v in tasks_raw.items()}
        except Exception as e:
            logger.error(f"Failed to get active tasks from Redis: {e}")
            return {}

    async def add_active_task(self, task_id: str, task_data: Dict[str, Any]) -> None:
        """添加或更新任务"""
        key = f"{REDIS_PREFIX}active_tasks"
        try:
            await self.redis.hset(key, task_id, json.dumps(task_data))
        except Exception as e:
            logger.error(f"Failed to add active task to Redis: {e}")

    async def remove_active_task(self, task_id: str) -> None:
        """移除任务"""
        key = f"{REDIS_PREFIX}active_tasks"
        try:
            await self.redis.hdel(key, task_id)
        except Exception as e:
            logger.error(f"Failed to remove active task from Redis: {e}")

    async def increment_user_concurrency(self, user_id: int) -> int:
        """增加用户并发数"""
        key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
        try:
            # 使用事务保证自增和设置过期时间的原子性，防止死锁
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                # 设置 1 小时过期时间作为兜底，防止异常导致计数器永远不降
                pipe.expire(key, 3600)
                results = await pipe.execute()
                return results[0]
        except Exception as e:
            logger.error(f"Failed to increment user concurrency: {e}")
            return 0

    async def decrement_user_concurrency(self, user_id: int) -> int:
        """减少用户并发数"""
        key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
        try:
            val = await self.redis.decr(key)
            if val < 0:
                await self.redis.set(key, 0)
                return 0
            return val
        except Exception as e:
            logger.error(f"Failed to decrement user concurrency: {e}")
            return 0

    async def get_user_concurrency(self, user_id: int) -> int:
        """获取用户当前并发数"""
        key = f"{REDIS_PREFIX}user_concurrency:{user_id}"
        try:
            val = await self.redis.get(key)
            return int(val) if val else 0
        except Exception as e:
            logger.error(f"Failed to get user concurrency: {e}")
            return 0

    async def close(self):
        """关闭连接"""
        await self.redis.aclose()

redis_client = RedisClient()
