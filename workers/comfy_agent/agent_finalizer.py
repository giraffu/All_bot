from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Awaitable, Callable

from agent_runtime_types import TaskExecutionContext
from agent_workflow_execution import TaskExecutionTimeoutError


class AgentFinalizer:
    def __init__(self, *, agent: Any, logger) -> None:
        self.agent = agent
        self.logger = logger

    def reset_execution_for_retry(
        self,
        execution: TaskExecutionContext,
        *,
        seed: int,
    ) -> dict[str, Any]:
        if execution.prompt_id:
            self.agent._prompt_executions.pop(execution.prompt_id, None)
        execution.prompt_id = None
        execution.task_result = None
        execution.task_result_priority = -1
        execution.task_error = None
        execution.completed_event = asyncio.Event()
        retry_params = dict(execution.params)
        retry_params["seed"] = seed
        execution.params = retry_params
        return retry_params

    async def _reserve_comfy_slot_for_retry(
        self,
        execution: TaskExecutionContext,
    ) -> None:
        """Move a quality retry back into the GPU phase without over-admission."""
        while True:
            async with self.agent._claim_lock:
                other_executions = {
                    task_id: candidate
                    for task_id, candidate in self.agent._executions.items()
                    if task_id != execution.task_id
                }
                admission = self.agent._pipeline_admission
                if (
                    admission.comfy_inflight_count(other_executions)
                    < admission.max_comfy_inflight
                ):
                    execution.phase = "preparing"
                    return
            await asyncio.sleep(0.1)

    async def retry_execution_after_quality_issue(
        self,
        execution: TaskExecutionContext,
        *,
        issue_reason: str,
        retry_number: int,
        quality_retry_attempts: int,
        agent_id: str,
        submit_task_workflow_func: Callable[..., Awaitable[Any]],
        wait_for_task_completion_func: Callable[..., Awaitable[bool]],
    ) -> bool:
        task_id = execution.task_id
        task_type = execution.task_type
        retry_seed = random.randint(1, 1125899906842624)
        retry_params = self.reset_execution_for_retry(execution, seed=retry_seed)
        self.logger.warning(
            "Retrying i2i_pro task %s after output quality issue (%s), attempt %s/%s",
            task_id,
            issue_reason,
            retry_number,
            quality_retry_attempts,
        )
        await self._reserve_comfy_slot_for_retry(execution)
        await submit_task_workflow_func(
            task_id=task_id,
            task_type=task_type,
            params=retry_params,
            execution=execution,
            patcher=self.agent.patcher,
            comfy_client=self.agent.comfy_client,
            wait_for_comfy_ready_func=self.agent._wait_for_comfy_ready,
            report_status_func=self.agent.report_status,
            agent_id=agent_id,
            logger=self.logger,
        )
        execution.params = dict(retry_params)
        self.agent._register_prompt_execution(execution)
        execution.phase = "queued"
        await self.agent.report_status(task_id, "running", execution_phase="queued")
        return await wait_for_task_completion_func(
            task_id=task_id,
            execution=execution,
            check_task_cancelled_func=self.agent.check_task_cancelled,
            logger=self.logger,
            comfy_client=self.agent.comfy_client,
            task_type=task_type,
            timeout_seconds=self.agent._completion_timeout_seconds_for_task(task_type),
        )

    async def materialize_outputs_with_quality_retry(
        self,
        *,
        execution: TaskExecutionContext,
        task_type: str,
        quality_retry_attempts: int,
        agent_id: str,
        submit_task_workflow_func: Callable[..., Awaitable[Any]],
        wait_for_task_completion_func: Callable[..., Awaitable[bool]],
        resolve_execution_result_from_history_func: Callable[..., Awaitable[Any]],
        materialize_task_outputs_func: Callable[..., Awaitable[Any]],
        assess_materialized_output_quality_func: Callable[..., Awaitable[Any]],
        result_history_timeout_seconds: float = 10.0,
        result_history_poll_seconds: float = 0.25,
    ):
        quality_retry_count = 0
        while True:
            await self._wait_for_execution_result(
                execution=execution,
                task_type=task_type,
                timeout_seconds=result_history_timeout_seconds,
                poll_seconds=result_history_poll_seconds,
                resolve_execution_result_from_history_func=(
                    resolve_execution_result_from_history_func
                ),
            )

            materialized_outputs = await materialize_task_outputs_func(
                comfy_client=self.agent.comfy_client,
                execution=execution,
                task_type=task_type,
                logger=self.logger,
                artifact_roots=getattr(self.agent, "_comfy_artifact_roots", None),
            )
            issue = await assess_materialized_output_quality_func(
                task_type=task_type,
                params=execution.params,
                outputs=materialized_outputs,
                comfy_client=self.agent.comfy_client,
                logger=self.logger,
            )
            if issue is None:
                return materialized_outputs

            if quality_retry_count >= quality_retry_attempts:
                raise RuntimeError(
                    "i2i_pro output quality check failed after retry: "
                    f"{issue.reason} metric={issue.metric:.2f} "
                    f"threshold={issue.threshold:.2f}"
                )

            quality_retry_count += 1
            task_completed = await self.retry_execution_after_quality_issue(
                execution,
                issue_reason=issue.reason,
                retry_number=quality_retry_count,
                quality_retry_attempts=quality_retry_attempts,
                agent_id=agent_id,
                submit_task_workflow_func=submit_task_workflow_func,
                wait_for_task_completion_func=wait_for_task_completion_func,
            )
            if not task_completed:
                return None

    async def _wait_for_execution_result(
        self,
        *,
        execution: TaskExecutionContext,
        task_type: str,
        timeout_seconds: float,
        poll_seconds: float,
        resolve_execution_result_from_history_func: Callable[..., Awaitable[Any]],
    ) -> None:
        loop = asyncio.get_running_loop()
        bounded_timeout = max(0.0, timeout_seconds)
        deadline = loop.time() + bounded_timeout
        attempts = 0
        while True:
            attempts += 1
            await resolve_execution_result_from_history_func(
                comfy_client=self.agent.comfy_client,
                execution=execution,
                task_type=task_type,
                logger=self.logger,
            )
            if execution.task_result:
                if attempts > 1:
                    self.logger.info(
                        "ComfyUI history exposed the result for task %s after %s reads",
                        execution.task_id,
                        attempts,
                    )
                return

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    "Task completed but no result path appeared in ComfyUI history "
                    f"within {bounded_timeout:.1f}s"
                )
            if attempts == 1:
                self.logger.warning(
                    "Task %s completed before its result was visible in ComfyUI history; "
                    "retrying for up to %.1fs",
                    execution.task_id,
                    bounded_timeout,
                )
            await asyncio.sleep(min(max(0.0, poll_seconds), remaining))

    async def finalize_execution(
        self,
        execution: TaskExecutionContext,
        *,
        cancel_lock_on_pop: bool,
        upload_sidecar_url: str,
        result_spool_dir: str,
        result_bucket: str,
        wan22_timeout_exit_code: int,
        quality_retry_attempts: int,
        agent_id: str,
        submit_task_workflow_func: Callable[..., Awaitable[Any]],
        wait_for_task_completion_func: Callable[..., Awaitable[bool]],
        resolve_execution_result_from_history_func: Callable[..., Awaitable[Any]],
        materialize_task_outputs_func: Callable[..., Awaitable[Any]],
        assess_materialized_output_quality_func: Callable[..., Awaitable[Any]],
        spool_materialized_outputs_func: Callable[..., Awaitable[Any]],
        upload_spooled_outputs_via_sidecar_func: Callable[..., Awaitable[Any]],
        upload_materialized_outputs_func: Callable[..., Awaitable[Any]],
        report_materialized_outputs_func: Callable[..., Awaitable[Any]],
        result_history_timeout_seconds: float = 10.0,
        result_history_poll_seconds: float = 0.25,
    ) -> None:
        task_id = execution.task_id
        task_type = execution.task_type
        exit_after_timeout = False
        try:
            task_completed = await wait_for_task_completion_func(
                task_id=task_id,
                execution=execution,
                check_task_cancelled_func=self.agent.check_task_cancelled,
                logger=self.logger,
                comfy_client=self.agent.comfy_client,
                task_type=task_type,
                timeout_seconds=self.agent._completion_timeout_seconds_for_task(
                    task_type
                ),
            )
            if not task_completed:
                await self.agent.report_cancelled(task_id)
                return

            execution.phase = "gpu_done"
            await self.agent.report_status(
                task_id,
                "running",
                execution_phase="gpu_done",
                set_current=False,
            )
            async with self.agent._delivery_gate.slot():
                execution.phase = "delivering"
                await self.agent.report_status(
                    task_id,
                    "running",
                    execution_phase="delivering",
                    set_current=False,
                )
                delivered = await self._deliver_execution(
                    execution=execution,
                    cancel_lock_on_pop=cancel_lock_on_pop,
                    upload_sidecar_url=upload_sidecar_url,
                    result_spool_dir=result_spool_dir,
                    result_bucket=result_bucket,
                    quality_retry_attempts=quality_retry_attempts,
                    agent_id=agent_id,
                    submit_task_workflow_func=submit_task_workflow_func,
                    wait_for_task_completion_func=wait_for_task_completion_func,
                    resolve_execution_result_from_history_func=(
                        resolve_execution_result_from_history_func
                    ),
                    materialize_task_outputs_func=materialize_task_outputs_func,
                    assess_materialized_output_quality_func=(
                        assess_materialized_output_quality_func
                    ),
                    spool_materialized_outputs_func=spool_materialized_outputs_func,
                    upload_spooled_outputs_via_sidecar_func=(
                        upload_spooled_outputs_via_sidecar_func
                    ),
                    upload_materialized_outputs_func=upload_materialized_outputs_func,
                    report_materialized_outputs_func=report_materialized_outputs_func,
                    result_history_timeout_seconds=result_history_timeout_seconds,
                    result_history_poll_seconds=result_history_poll_seconds,
                )
                if not delivered:
                    return
            self.agent._record_task_success_for_health()
            self.logger.info("Task %s completed successfully", task_id)

        except Exception as exc:
            self.logger.error("Task %s failed: %s", task_id, exc)
            if (
                isinstance(exc, TaskExecutionTimeoutError)
                and task_type == "wan22_video_v2"
            ):
                await self.agent._interrupt_comfy_for_wan22_timeout(execution)
                exit_after_timeout = self.agent._should_self_restart_after_timeout(
                    execution,
                    exc,
                )
            self.agent._record_task_failure_for_health(exc)
            await self.agent.report_status(task_id, "failed", error=str(exc))
        finally:
            self.agent._clear_task_execution(execution)
            self.agent._cleanup_input_paths(execution.downloaded_input_paths)
            self.agent._cleanup_comfy_artifacts(execution.comfy_input_artifacts)
        if exit_after_timeout:
            self.logger.error(
                "Exiting agent after wan22_video_v2 timeout so the supervisor can restart a clean ComfyUI runtime"
            )
            os._exit(wan22_timeout_exit_code)

    async def _deliver_execution(
        self,
        *,
        execution: TaskExecutionContext,
        cancel_lock_on_pop: bool,
        upload_sidecar_url: str,
        result_spool_dir: str,
        result_bucket: str,
        quality_retry_attempts: int,
        agent_id: str,
        submit_task_workflow_func: Callable[..., Awaitable[Any]],
        wait_for_task_completion_func: Callable[..., Awaitable[bool]],
        resolve_execution_result_from_history_func: Callable[..., Awaitable[Any]],
        materialize_task_outputs_func: Callable[..., Awaitable[Any]],
        assess_materialized_output_quality_func: Callable[..., Awaitable[Any]],
        spool_materialized_outputs_func: Callable[..., Awaitable[Any]],
        upload_spooled_outputs_via_sidecar_func: Callable[..., Awaitable[Any]],
        upload_materialized_outputs_func: Callable[..., Awaitable[Any]],
        report_materialized_outputs_func: Callable[..., Awaitable[Any]],
        result_history_timeout_seconds: float,
        result_history_poll_seconds: float,
    ) -> bool:
        task_id = execution.task_id
        task_type = execution.task_type
        if not cancel_lock_on_pop and await self.agent.check_task_cancelled(task_id):
            self.logger.info(
                "Task %s was cancelled during execution, skipping upload.",
                task_id,
            )
            await self.agent.report_cancelled(task_id)
            return False

        try:
            materialized_outputs = await self.materialize_outputs_with_quality_retry(
                execution=execution,
                task_type=task_type,
                quality_retry_attempts=quality_retry_attempts,
                agent_id=agent_id,
                submit_task_workflow_func=submit_task_workflow_func,
                wait_for_task_completion_func=wait_for_task_completion_func,
                resolve_execution_result_from_history_func=(
                    resolve_execution_result_from_history_func
                ),
                materialize_task_outputs_func=materialize_task_outputs_func,
                assess_materialized_output_quality_func=(
                    assess_materialized_output_quality_func
                ),
                result_history_timeout_seconds=result_history_timeout_seconds,
                result_history_poll_seconds=result_history_poll_seconds,
            )
            if materialized_outputs is None:
                await self.agent.report_cancelled(task_id)
                return False
            if upload_sidecar_url:
                spooled_outputs = await spool_materialized_outputs_func(
                    outputs=materialized_outputs,
                    spool_dir=result_spool_dir,
                    task_id=task_id,
                    logger=self.logger,
                )
                uploaded_outputs_payload = (
                    await upload_spooled_outputs_via_sidecar_func(
                        sidecar_url=upload_sidecar_url,
                        result_bucket=result_bucket,
                        task_id=task_id,
                        spooled_outputs=spooled_outputs,
                        logger=self.logger,
                    )
                )
            else:
                uploaded_outputs_payload = await upload_materialized_outputs_func(
                    minio_client=self.agent.minio_client,
                    result_bucket=result_bucket,
                    task_id=task_id,
                    outputs=materialized_outputs,
                    logger=self.logger,
                )
        except Exception as exc:
            self.logger.error("Failed to fetch or upload result: %s", exc)
            raise Exception(f"Result processing failed: {exc}") from exc

        if "result_path" not in uploaded_outputs_payload:
            uploaded_outputs_payload = {
                "result_path": execution.task_result,
                "extra_outputs": uploaded_outputs_payload,
            }
        execution.phase = "reporting_complete"
        await report_materialized_outputs_func(
            report_complete_func=self.agent.report_complete,
            task_id=task_id,
            uploaded_outputs_payload=uploaded_outputs_payload,
            result_path=execution.task_result,
        )
        self.agent._cleanup_comfy_artifacts(
            list(getattr(materialized_outputs, "source_artifacts", []) or [])
        )
        self.agent._cleanup_task_comfy_artifacts(task_id)
        return True
