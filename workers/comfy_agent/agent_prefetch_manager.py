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

    def eligible_prefetch_types(self) -> str:
        pop_types = self.agent._build_pop_params(pipeline=True).get("types", "")
        eligible_types = {
            task_type.strip() for task_type in pop_types.split(",") if task_type.strip()
        } & self.agent._prefetch_task_types
        return ",".join(sorted(eligible_types))

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
                self.agent._cleanup_comfy_artifacts(
                    cached.get("comfy_input_artifacts", [])
                )

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
            self.agent._cleanup_comfy_artifacts(cached.get("comfy_input_artifacts", []))
            return None
        self.logger.info("Using prefetched inputs for task %s", task_id)
        return cached

    async def prefetch_next_task_inputs(
        self,
        *,
        prefetch_enabled: bool,
        prefetch_depth: int,
        cache_dir: str,
        reserve_task: bool = False,
    ) -> None:
        if not prefetch_enabled or prefetch_depth <= 0:
            return
        if self.agent._prefetch_cache:
            return

        prefetch_types = self.eligible_prefetch_types()
        if not prefetch_types:
            return
        params = {"limit": prefetch_depth, "types": prefetch_types}
        downloaded_input_paths: list[str] = []
        comfy_input_artifacts: list[Any] = []

        try:
            endpoint = "/api/agent/task/peek"
            if reserve_task:
                endpoint = "/api/agent/task/pop"
                params = self.agent._build_pop_params(pipeline=True)
                params["types"] = prefetch_types
                async with self.agent._claim_lock:
                    if not self.agent._pipeline_admission.can_reserve_task(
                        self.agent._executions,
                        self.agent._reserved_prefetch_task,
                    ):
                        return
                    response = await self.agent._master_get(endpoint, params=params)
                    if response.status_code != 200:
                        self.logger.debug(
                            "Prefetch pop returned HTTP %s",
                            response.status_code,
                        )
                        return
                    task = response.json().get("task")
                    task_id = str((task or {}).get("task_id", ""))
                    if task_id in self.agent._executions:
                        await self.agent._acknowledge_redelivered_task(task_id)
                        self.agent._discard_prefetched_task(task_id)
                        return
                    if task_id:
                        self.agent._reserved_prefetch_task = task
            else:
                response = await self.agent._master_get(endpoint, params=params)
                if response.status_code != 200:
                    self.logger.debug(
                        "Prefetch peek returned HTTP %s",
                        response.status_code,
                    )
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
            await self.agent._prepare_task_inputs(
                params=prefetch_params,
                task_type=task_type,
                downloaded_input_paths=downloaded_input_paths,
                uploaded_input_artifacts=comfy_input_artifacts,
                comfy_filename_prefix=task_id,
                comfy_input_dir=cache_dir,
            )
            self.discard_prefetch_cache()
            self.agent._prefetch_cache[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "params": prefetch_params,
                "downloaded_input_paths": downloaded_input_paths,
                "comfy_input_artifacts": comfy_input_artifacts,
            }
            self.logger.info(
                "Prefetched inputs for pending task %s (%s)",
                task_id,
                task_type,
            )
        except asyncio.CancelledError:
            self.cleanup_input_paths(downloaded_input_paths)
            self.agent._cleanup_comfy_artifacts(comfy_input_artifacts)
            raise
        except Exception as exc:
            self.cleanup_input_paths(downloaded_input_paths)
            self.agent._cleanup_comfy_artifacts(comfy_input_artifacts)
            self.logger.warning("Prefetch failed: %s", exc)

    def schedule_prefetch(
        self,
        *,
        current_task_type: str,
        prefetch_enabled: bool,
        prefetch_depth: int,
        cache_dir: str,
        reserve_task: bool = False,
    ) -> None:
        if not prefetch_enabled:
            return
        if not self.should_prefetch_task_type(
            current_task_type,
            prefetch_enabled=prefetch_enabled,
            prefetch_depth=prefetch_depth,
        ):
            return
        if reserve_task and not self.agent._pipeline_admission.can_reserve_task(
            self.agent._executions,
            self.agent._reserved_prefetch_task,
        ):
            return
        if self.agent._prefetch_task and not self.agent._prefetch_task.done():
            return
        self.agent._prefetch_task = asyncio.create_task(
            self.prefetch_next_task_inputs(
                prefetch_enabled=prefetch_enabled,
                prefetch_depth=prefetch_depth,
                cache_dir=cache_dir,
                reserve_task=reserve_task,
            )
        )
