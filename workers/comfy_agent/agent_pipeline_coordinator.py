from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from asgi_correlation_id import correlation_id

from agent_runtime_types import TaskExecutionContext


class AgentPipelineCoordinator:
    def __init__(self, *, agent: Any, logger) -> None:
        self.agent = agent
        self.logger = logger

    @staticmethod
    def pipeline_enabled_for_task_type(
        task_type: str,
        *,
        pipeline_enabled: bool,
        pipeline_max_running_tasks: int,
        pipeline_task_types: set[str],
    ) -> bool:
        if not pipeline_enabled or pipeline_max_running_tasks <= 1:
            return False
        if "all" in pipeline_task_types:
            return True
        return task_type in pipeline_task_types

    @staticmethod
    def pipeline_pop_types(
        *,
        supported_task_types: str,
        pipeline_task_types: set[str],
    ) -> str:
        supported_types = {
            task_type.strip()
            for task_type in supported_task_types.split(",")
            if task_type.strip()
        }
        if not pipeline_task_types or "all" in pipeline_task_types:
            return supported_task_types
        if not supported_types:
            return ",".join(sorted(pipeline_task_types))
        return ",".join(sorted(supported_types & pipeline_task_types))

    def build_pop_params(
        self,
        *,
        agent_id: str,
        supported_task_types: str,
        preferred_task_types: str,
        pipeline_task_types: set[str],
        cancel_lock_on_pop: bool,
        pipeline: bool = False,
    ) -> dict[str, str]:
        params: dict[str, str] = {"agent_id": agent_id}
        types = (
            self.pipeline_pop_types(
                supported_task_types=supported_task_types,
                pipeline_task_types=pipeline_task_types,
            )
            if pipeline
            else supported_task_types
        )
        if types:
            params["types"] = types
        request_types = {
            task_type.strip() for task_type in types.split(",") if task_type.strip()
        }
        request_preferred = [
            task_type.strip()
            for task_type in preferred_task_types.split(",")
            if task_type.strip() and task_type.strip() in request_types
        ]
        if request_preferred:
            params["preferred_types"] = ",".join(request_preferred)
        if cancel_lock_on_pop:
            params["cancel_lock"] = "true"
        return params

    async def pop_next_task(
        self,
        *,
        agent_id: str,
        supported_task_types: str,
        preferred_task_types: str,
        pipeline_task_types: set[str],
        cancel_lock_on_pop: bool,
        pipeline: bool = False,
    ) -> dict[str, Any] | None:
        response = await self.agent._master_get(
            "/api/agent/task/pop",
            params=self.build_pop_params(
                agent_id=agent_id,
                supported_task_types=supported_task_types,
                preferred_task_types=preferred_task_types,
                pipeline_task_types=pipeline_task_types,
                cancel_lock_on_pop=cancel_lock_on_pop,
                pipeline=pipeline,
            ),
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("task")
        if response.status_code != 404:
            self.logger.warning(
                "Unexpected response from master: %s",
                response.status_code,
            )
        return None

    @staticmethod
    def parse_task_params(task: dict[str, Any]) -> dict[str, Any]:
        params = task.get("params")
        if isinstance(params, str):
            try:
                return json.loads(params)
            except Exception:
                return {}
        if isinstance(params, dict):
            return dict(params)
        return {}

    async def prepare_and_submit_task(
        self,
        task: dict[str, Any],
        *,
        allow_cancel_check: bool,
        cancel_lock_on_pop: bool,
        agent_id: str,
        submit_task_workflow_func: Callable[..., Awaitable[Any]],
        before_submit_func: Callable[[], Awaitable[None]] | None = None,
    ) -> TaskExecutionContext | None:
        trace_id = task.get("trace_id", "")
        if trace_id:
            correlation_id.set(trace_id)

        task_id = str(task.get("task_id", ""))
        if not task_id:
            self.logger.error("Received task without task_id")
            return None

        task_type = str(task.get("type", ""))
        params = self.parse_task_params(task)

        self.logger.info("Processing task %s of type %s", task_id, task_type)
        execution = self.agent._start_task_execution(
            task_id=task_id,
            task_type=task_type,
        )
        downloaded_input_paths = execution.downloaded_input_paths

        if allow_cancel_check and await self.agent.check_task_cancelled(task_id):
            self.logger.info("Task %s was cancelled before processing.", task_id)
            self.agent._discard_prefetch_cache(except_task_id=None)
            await self.agent.report_cancelled(task_id)
            self.agent._clear_task_execution(execution)
            return None

        await self.agent.report_status(
            task_id,
            "running",
            execution_phase="preparing",
            cancel_locked=cancel_lock_on_pop,
        )

        await self.agent._wait_for_prefetch_settle()
        prefetched_inputs = self.agent._consume_prefetched_inputs(
            task_id=task_id,
            task_type=task_type,
        )
        if prefetched_inputs:
            params = dict(prefetched_inputs["params"])
            downloaded_input_paths.extend(
                prefetched_inputs.get("downloaded_input_paths", [])
            )
        else:
            await self.agent._cancel_prefetch_task()
            await self.agent._prepare_task_inputs(
                params=params,
                downloaded_input_paths=downloaded_input_paths,
            )

        if before_submit_func is not None:
            await before_submit_func()
        await submit_task_workflow_func(
            task_id=task_id,
            task_type=task_type,
            params=params,
            execution=execution,
            patcher=self.agent.patcher,
            comfy_client=self.agent.comfy_client,
            wait_for_comfy_ready_func=self.agent._wait_for_comfy_ready,
            report_status_func=self.agent.report_status,
            agent_id=agent_id,
            logger=self.logger,
        )
        execution.params = dict(params)
        self.agent._register_prompt_execution(execution)
        execution.phase = "queued"
        await self.agent.report_status(task_id, "running", execution_phase="queued")
        self.agent._schedule_prefetch(current_task_type=task_type)
        return execution

    async def launch_pipeline_task(
        self,
        task: dict[str, Any],
        *,
        cancel_lock_on_pop: bool,
    ) -> None:
        task_id = str(task.get("task_id", ""))
        try:
            execution = await self.agent._prepare_and_submit_task(
                task,
                allow_cancel_check=not cancel_lock_on_pop,
            )
            if not execution:
                return
            finalizer_task = asyncio.create_task(self.agent._finalize_execution(execution))
            self.agent._track_execution_task(finalizer_task)
        except Exception as exc:
            self.logger.error(
                "Task %s failed before pipeline submission: %s",
                task_id,
                exc,
            )
            self.agent._record_task_failure_for_health(exc)
            if task_id:
                await self.agent.report_status(task_id, "failed", error=str(exc))
            execution = self.agent._executions.get(task_id)
            if execution:
                self.agent._clear_task_execution(execution)
                self.agent._cleanup_input_paths(execution.downloaded_input_paths)
