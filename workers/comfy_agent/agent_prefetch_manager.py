from __future__ import annotations

import asyncio
import json
import os
from typing import Any


class AgentPrefetchManager:
    def __init__(self, *, agent: Any, logger) -> None:
        self.agent = agent
        self.logger = logger

    @staticmethod
    def parse_task_params(task: dict[str, Any]) -> dict[str, Any]:
        params_str = task.get("params", "{}")
        if isinstance(params_str, str):
            parsed = json.loads(params_str)
        else:
            parsed = params_str
        return dict(parsed or {})

    def should_prefetch_task_type(
        self,
        task_type: str,
        *,
        prefetch_enabled: bool,
        prefetch_depth: int,
    ) -> bool:
        if not prefetch_enabled or prefetch_depth <= 0:
            return False
        return task_type in self.agent._prefetch_task_types

    def cleanup_input_paths(self, paths: list[str]) -> None:
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.logger.info("Cleaned up input file: %s", path)
            except Exception as exc:
                self.logger.warning("Failed to clean up input file %s: %s", path, exc)

    def discard_prefetch_cache(self, *, except_task_id: str | None = None) -> None:
        task_ids = list(self.agent._prefetch_cache.keys())
        for cached_task_id in task_ids:
            if except_task_id and cached_task_id == except_task_id:
                continue
            cached = self.agent._prefetch_cache.pop(cached_task_id, None)
            if cached:
                self.cleanup_input_paths(cached.get("downloaded_input_paths", []))

    async def wait_for_prefetch_settle(
        self,
        *,
        consume_wait_seconds: float,
    ) -> None:
        if not self.agent._prefetch_task or self.agent._prefetch_task.done():
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(self.agent._prefetch_task),
                timeout=max(0.0, consume_wait_seconds),
            )
        except asyncio.TimeoutError:
            return
        except Exception as exc:
            self.logger.debug("Prefetch settle failed: %s", exc)

    async def cancel_prefetch_task(self) -> None:
        if not self.agent._prefetch_task or self.agent._prefetch_task.done():
            return
        self.agent._prefetch_task.cancel()
        try:
            await self.agent._prefetch_task
        except asyncio.CancelledError:
            pass

    def consume_prefetched_inputs(
        self,
        *,
        task_id: str,
        task_type: str,
    ) -> dict[str, Any] | None:
        cached = self.agent._prefetch_cache.pop(task_id, None)
        self.discard_prefetch_cache()
        if not cached:
            return None
        if cached.get("task_type") != task_type:
            self.cleanup_input_paths(cached.get("downloaded_input_paths", []))
            return None
        self.logger.info("Using prefetched inputs for task %s", task_id)
        return cached

    async def prefetch_next_task_inputs(
        self,
        *,
        task_type_filter: str | None,
        prefetch_enabled: bool,
        prefetch_depth: int,
        cache_dir: str,
    ) -> None:
        if not prefetch_enabled or prefetch_depth <= 0:
            return
        if self.agent._prefetch_cache:
            return

        params = {"limit": prefetch_depth}
        if task_type_filter and task_type_filter in self.agent._prefetch_task_types:
            prefetch_types = task_type_filter
        else:
            prefetch_types = ",".join(sorted(self.agent._prefetch_task_types))
        if prefetch_types:
            params["types"] = prefetch_types

        try:
            response = await self.agent._master_get(
                "/api/agent/task/peek",
                params=params,
            )
            if response.status_code != 200:
                self.logger.debug("Prefetch peek returned HTTP %s", response.status_code)
                return
            task = response.json().get("task")
            if not task:
                return

            task_id = str(task.get("task_id", ""))
            task_type = str(task.get("type", ""))
            if not task_id or not self.should_prefetch_task_type(
                task_type,
                prefetch_enabled=prefetch_enabled,
                prefetch_depth=prefetch_depth,
            ):
                return

            prefetch_params = self.parse_task_params(task)
            downloaded_input_paths: list[str] = []
            await self.agent._prepare_task_inputs(
                params=prefetch_params,
                downloaded_input_paths=downloaded_input_paths,
                comfy_input_dir=cache_dir,
            )
            self.discard_prefetch_cache()
            self.agent._prefetch_cache[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "params": prefetch_params,
                "downloaded_input_paths": downloaded_input_paths,
            }
            self.logger.info(
                "Prefetched inputs for pending task %s (%s)",
                task_id,
                task_type,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.warning("Prefetch failed: %s", exc)

    def schedule_prefetch(
        self,
        *,
        current_task_type: str,
        prefetch_enabled: bool,
        prefetch_depth: int,
        cache_dir: str,
    ) -> None:
        if not prefetch_enabled:
            return
        if not self.should_prefetch_task_type(
            current_task_type,
            prefetch_enabled=prefetch_enabled,
            prefetch_depth=prefetch_depth,
        ):
            return
        if self.agent._prefetch_task and not self.agent._prefetch_task.done():
            return
        self.agent._prefetch_task = asyncio.create_task(
            self.prefetch_next_task_inputs(
                task_type_filter=current_task_type,
                prefetch_enabled=prefetch_enabled,
                prefetch_depth=prefetch_depth,
                cache_dir=cache_dir,
            )
        )
