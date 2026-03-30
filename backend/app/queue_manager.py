import json
import time
import uuid
from typing import Optional, Dict, Any, Tuple
from redis.asyncio import Redis
from app.config import settings
from app.models import TaskStatus, TaskType

class QueueManager:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.pending_key = "comfy:queue:pending"
        self.running_key = "comfy:queue:running"
        self.task_prefix = "comfy:task:"
        self.agent_heartbeat_prefix = "comfy:agent:heartbeat:"
        self.ttl = 86400  # 24 hours

    async def enqueue_task(self, task_type: TaskType, params: Dict[str, Any], priority: int = 0) -> str:
        task_id = str(uuid.uuid4())
        task_key = f"{self.task_prefix}{task_id}"
        
        # Create task metadata
        task_data = {
            "task_id": task_id,
            "type": task_type,
            "status": TaskStatus.PENDING,
            "priority": priority,
            "params": json.dumps(params),
            "created_at": time.time(),
            "progress": 0.0,
            "error_msg": "",
            "result_path": ""
        }
        
        # Save task details
        await self.redis.hset(task_key, mapping=task_data)
        await self.redis.expire(task_key, self.ttl)
        
        # Add to priority queue
        # Priority acceleration: Each priority level equals 60 seconds earlier enqueue time.
        # This prevents starvation: a low priority task waiting >60s will beat a new high priority task.
        score = time.time() - (priority * 60)
        await self.redis.zadd(self.pending_key, {task_id: score})
        
        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task_key = f"{self.task_prefix}{task_id}"
        if not await self.redis.exists(task_key):
            return None
            
        data = await self.redis.hgetall(task_key)
        # Convert bytes to string
        return {k.decode(): v.decode() for k, v in data.items()}

    async def dequeue_task(self, allowed_types: Optional[list[str]] = None) -> Optional[Tuple[str, float]]:
        # If no types specified, pop the top task as before
        if not allowed_types:
            result = await self.redis.zpopmin(self.pending_key)
            if not result:
                return None
            task_id, score = result[0]
            task_id = task_id.decode() if isinstance(task_id, bytes) else task_id
            await self._mark_task_running(task_id)
            return task_id, score

        # If specific types are allowed, find the highest priority task matching those types
        # We fetch a batch of tasks to minimize Redis roundtrips
        batch_size = 50
        offset = 0
        while True:
            tasks_with_scores = await self.redis.zrange(self.pending_key, offset, offset + batch_size - 1, withscores=True)
            if not tasks_with_scores:
                return None
            
            for task_id_bytes, score in tasks_with_scores:
                task_id = task_id_bytes.decode() if isinstance(task_id_bytes, bytes) else task_id_bytes
                task_key = f"{self.task_prefix}{task_id}"
                
                # Check task type
                task_type_bytes = await self.redis.hget(task_key, "type")
                if not task_type_bytes:
                    continue
                
                task_type = task_type_bytes.decode() if isinstance(task_type_bytes, bytes) else task_type_bytes
                if task_type in allowed_types:
                    # Atomically remove from pending and check if we succeeded (to avoid race conditions)
                    removed = await self.redis.zrem(self.pending_key, task_id)
                    if removed:
                        await self._mark_task_running(task_id)
                        return task_id, score
            
            offset += batch_size

    async def _mark_task_running(self, task_id: str):
        # Move to running set
        await self.redis.sadd(self.running_key, task_id)
        # Update status
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, "status", TaskStatus.RUNNING)

    async def set_prompt_id(self, task_id: str, prompt_id: str):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, "comfy_prompt_id", prompt_id)
        # Store reverse mapping for 1 hour
        await self.redis.setex(f"comfy:prompt:{prompt_id}", 3600, task_id)

    async def get_task_by_prompt_id(self, prompt_id: str) -> Optional[str]:
        task_id_bytes = await self.redis.get(f"comfy:prompt:{prompt_id}")
        return task_id_bytes.decode() if task_id_bytes else None

    async def complete_task(self, task_id: str, result_path: str):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, mapping={
            "status": TaskStatus.DONE,
            "result_path": result_path,
            "progress": 1.0
        })
        await self.redis.srem(self.running_key, task_id)

    async def fail_task(self, task_id: str, error_msg: str):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, mapping={
            "status": TaskStatus.ERROR,
            "error_msg": error_msg
        })
        await self.redis.srem(self.running_key, task_id)

    async def update_progress(self, task_id: str, progress: float):
        task_key = f"{self.task_prefix}{task_id}"
        await self.redis.hset(task_key, "progress", progress)
        
    async def get_queue_position(self, task_id: str) -> Optional[int]:
        return await self.redis.zrank(self.pending_key, task_id)

    async def get_queue_size(self) -> int:
        return await self.redis.zcard(self.pending_key)
        
    async def get_active_workers_count(self) -> int:
        # Get count of agents that have sent a heartbeat recently
        cursor = 0
        count = 0
        pattern = f"{self.agent_heartbeat_prefix}*"
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            count += len(keys)
            if cursor == 0:
                break
        return count

    async def update_agent_heartbeat(self, agent_id: str, types: str, status: str):
        key = f"{self.agent_heartbeat_prefix}{agent_id}"
        data = {
            "types": types,
            "status": status,
            "last_seen": time.time()
        }
        await self.redis.hset(key, mapping=data)
        # Agent heartbeats every 10-15s, expire if no heartbeat for 30s
        await self.redis.expire(key, 30)

    async def get_queue_metrics_by_type(self) -> Dict[str, int]:
        task_ids = await self.redis.zrange(self.pending_key, 0, -1)
        
        # Initialize counts for all known types to 0
        counts = {t.value: 0 for t in TaskType}
        
        if not task_ids:
            return counts
            
        # Use pipeline to fetch types efficiently
        pipeline = self.redis.pipeline()
        for task_id in task_ids:
            task_id_str = task_id.decode() if isinstance(task_id, bytes) else task_id
            task_key = f"{self.task_prefix}{task_id_str}"
            pipeline.hget(task_key, "type")
            
        types = await pipeline.execute()
        
        for t in types:
            if t:
                type_str = t.decode() if isinstance(t, bytes) else t
                if type_str in counts:
                    counts[type_str] += 1
                else:
                    counts[type_str] = counts.get(type_str, 0) + 1
                    
        return counts

    async def clear_running_tasks(self):
        await self.redis.delete(self.running_key)
