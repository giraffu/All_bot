import json
import logging
import uuid
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

    async def add_pending_web_finalizer(
        self,
        registry_task_id: str,
        finalizer_data: Dict[str, Any],
    ) -> None:
        key = f"{REDIS_PREFIX}pending_web_finalizers"
        try:
            await self.redis.hset(key, registry_task_id, json.dumps(finalizer_data))
        except Exception as e:
            logger.error(
                f"Failed to persist pending web finalizer for {registry_task_id}: {e}"
            )

    async def get_pending_web_finalizer(
        self,
        registry_task_id: str,
    ) -> Dict[str, Any] | None:
        key = f"{REDIS_PREFIX}pending_web_finalizers"
        try:
            raw_data = await self.redis.hget(key, registry_task_id)
            if not raw_data:
                return None
            return json.loads(raw_data)
        except Exception as e:
            logger.error(
                f"Failed to get pending web finalizer for {registry_task_id}: {e}"
            )
            return None

    async def get_pending_web_finalizers(self) -> Dict[str, Any]:
        key = f"{REDIS_PREFIX}pending_web_finalizers"
        try:
            finalizers_raw = await self.redis.hgetall(key)
            return {k: json.loads(v) for k, v in finalizers_raw.items()}
        except Exception as e:
            logger.error(f"Failed to get pending web finalizers from Redis: {e}")
            return {}

    async def remove_pending_web_finalizer(self, registry_task_id: str) -> None:
        key = f"{REDIS_PREFIX}pending_web_finalizers"
        try:
            await self.redis.hdel(key, registry_task_id)
        except Exception as e:
            logger.error(
                f"Failed to remove pending web finalizer for {registry_task_id}: {e}"
            )

    async def acquire_pending_web_finalizer_lock(
        self,
        registry_task_id: str,
        ttl_seconds: int = 900,
    ) -> str | None:
        key = f"{REDIS_PREFIX}pending_web_finalizer_lock:{registry_task_id}"
        token = str(uuid.uuid4())
        try:
            locked = await self.redis.set(key, token, ex=ttl_seconds, nx=True)
            return token if locked else None
        except Exception as e:
            logger.error(
                "Failed to acquire pending web finalizer lock for %s: %s",
                registry_task_id,
                e,
            )
            return token

    async def release_pending_web_finalizer_lock(
        self,
        registry_task_id: str,
        token: str | None,
    ) -> None:
        if not token:
            return
        key = f"{REDIS_PREFIX}pending_web_finalizer_lock:{registry_task_id}"
        release_script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""
        try:
            await self.redis.eval(release_script, 1, key, token)
        except Exception as e:
            logger.error(
                "Failed to release pending web finalizer lock for %s: %s",
                registry_task_id,
                e,
            )

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

    async def get_gallery_submit_count(self, user_id: int) -> int:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        key = f"{REDIS_PREFIX}gallery_submit_count:{user_id}:{today}"
        try:
            count = await self.redis.get(key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(
                f"Failed to get gallery submit count for user {user_id}: {e}"
            )
            return 0

    async def set_comment_lock(self, user_id: int, ttl: int = 5) -> bool:
        """限制用户的发评频率防范脚本水军"""
        key = f"{REDIS_PREFIX}comment_lock:{user_id}"
        try:
            # nx=True 时若键已存在会返回 None，必须显式转换为 bool
            return bool(await self.redis.set(key, "1", ex=ttl, nx=True))
        except Exception as e:
            logger.error(f"Failed to set comment lock for user {user_id}: {e}")
            return True  # 容灾：如果Redis报错，放行

    async def delete_comment_lock(self, user_id: int) -> None:
        """删除用户评论频率锁，避免写库失败后残留限流"""
        key = f"{REDIS_PREFIX}comment_lock:{user_id}"
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete comment lock for user {user_id}: {e}")

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
