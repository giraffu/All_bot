import json
import logging
from typing import Any, Dict

import redis.asyncio as redis

from config import REDIS_PREFIX, REDIS_URL

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

    async def increment_gallery_submit(self, user_id: int) -> int:
        """增加每日投稿次数，并返回增加后的次数"""
        import datetime

        today = datetime.date.today().isoformat()
        key = f"{REDIS_PREFIX}gallery_submit_count:{user_id}:{today}"
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                # 设置 24 小时过期时间 (86400秒)，因为只管当天
                pipe.expire(key, 86400)
                results = await pipe.execute()
                return results[0]
        except Exception as e:
            logger.error(
                f"Failed to increment gallery submit count for user {user_id}: {e}"
            )
            return 0

    async def add_pending_refund(
        self, user_id: int, amount: int, reason: str, operator: str
    ) -> None:
        """添加退款失败记录到 Outbox 队列"""
        import time

        key = f"{REDIS_PREFIX}pending_refunds"
        data = {
            "user_id": user_id,
            "amount": amount,
            "reason": reason,
            "operator": operator,
            "timestamp": time.time(),
        }
        try:
            await self.redis.lpush(key, json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to add pending refund to Redis outbox: {e}")

    async def check_gallery_submit_limit(self, user_id: int, limit: int = 10) -> bool:
        """检查今日是否已超过投稿上限"""
        import datetime

        today = datetime.date.today().isoformat()
        key = f"{REDIS_PREFIX}gallery_submit_count:{user_id}:{today}"
        try:
            val = await self.redis.get(key)
            if val and int(val) >= limit:
                return False
            return True
        except Exception as e:
            logger.error(
                f"Failed to check gallery submit limit for user {user_id}: {e}"
            )
            return True  # 容灾：如果Redis报错，放行

    async def get_all_user_concurrencies(self) -> Dict[int, int]:
        """获取所有用户的并发锁状态"""
        pattern = f"{REDIS_PREFIX}user_concurrency:*"
        concurrencies = {}
        try:
            keys = await self.redis.keys(pattern)
            if not keys:
                return {}

            # 使用 pipeline 批量获取值
            async with self.redis.pipeline(transaction=False) as pipe:
                for key in keys:
                    pipe.get(key)
                values = await pipe.execute()

            prefix_len = len(f"{REDIS_PREFIX}user_concurrency:")
            for key, val in zip(keys, values):
                if val is not None and int(val) > 0:
                    user_id = int(key[prefix_len:])
                    concurrencies[user_id] = int(val)

            return concurrencies
        except Exception as e:
            logger.error(f"Failed to get user concurrencies: {e}")
            return {}

    async def close(self):
        """关闭连接"""
        await self.redis.aclose()


redis_client = RedisClient()
