from __future__ import annotations

from typing import Any, Callable


class AgentReportingClient:
    def __init__(
        self,
        *,
        master_client,
        logger,
        record_control_plane_success: Callable[[], None],
        record_control_plane_failure: Callable[[Exception | str], None],
    ) -> None:
        self.master_client = master_client
        self.logger = logger
        self._record_control_plane_success = record_control_plane_success
        self._record_control_plane_failure = record_control_plane_failure

    async def master_get(self, path: str, **kwargs):
        try:
            response = await self.master_client.get(path, **kwargs)
        except Exception as exc:
            self._record_control_plane_failure(exc)
            raise

        status_code = getattr(response, "status_code", 200)
        if status_code >= 500:
            self._record_control_plane_failure(
                f"GET {path} returned HTTP {status_code}"
            )
        else:
            self._record_control_plane_success()
        return response

    async def master_post(self, path: str, **kwargs):
        try:
            response = await self.master_client.post(path, **kwargs)
        except Exception as exc:
            self._record_control_plane_failure(exc)
            raise

        status_code = getattr(response, "status_code", 200)
        if status_code >= 500:
            self._record_control_plane_failure(
                f"POST {path} returned HTTP {status_code}"
            )
        else:
            self._record_control_plane_success()
        return response

    async def report_heartbeat(
        self,
        *,
        agent_id: str,
        supported_task_types: str,
        status: str,
        health_payload: dict[str, Any],
        pool_payload: dict[str, Any],
        runtime_manifest: dict[str, Any],
        executions: list[Any],
    ) -> None:
        try:
            await self.master_post(
                "/api/agent/task/heartbeat",
                json={
                    "agent_id": agent_id,
                    "types": supported_task_types,
                    "status": status,
                    **health_payload,
                    **pool_payload,
                    "runtime_manifest": runtime_manifest,
                },
            )
            for execution in executions:
                await self.master_post(
                    "/api/agent/task/task_heartbeat",
                    json={"task_id": execution.task_id, "agent_id": agent_id},
                )
        except Exception as exc:
            self.logger.debug("Failed to report heartbeat: %s", exc)

    async def report_status(
        self,
        *,
        task_id: str,
        agent_id: str,
        status: str,
        progress: float,
        error: str,
        execution_phase: str | None,
        cancel_locked: bool | None,
        set_current: bool,
        attempts: int,
        retry_base_seconds: float,
        retry_max_seconds: float,
        sleep_func,
    ) -> None:
        payload: dict[str, Any] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "status": status,
            "progress": progress,
            "error": error,
        }
        if execution_phase is not None:
            payload["execution_phase"] = execution_phase
        if cancel_locked is not None:
            payload["cancel_locked"] = cancel_locked
        if not set_current:
            payload["set_current"] = False

        for attempt in range(1, attempts + 1):
            try:
                response = await self.master_post(
                    "/api/agent/task/status",
                    json=payload,
                )
                status_code = getattr(response, "status_code", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Central API returned HTTP {status_code} for status report"
                    )
                return
            except Exception as exc:
                if attempt >= attempts:
                    self.logger.error(
                        "Failed to report status for task %s after %s attempts: %s",
                        task_id,
                        attempts,
                        exc,
                    )
                    return
                delay = min(
                    retry_base_seconds * (2 ** (attempt - 1)),
                    retry_max_seconds,
                )
                self.logger.debug(
                    "Failed to report status for task %s on attempt %s/%s; retrying in %.1fs: %s",
                    task_id,
                    attempt,
                    attempts,
                    delay,
                    exc,
                )
                await sleep_func(delay)

    async def report_complete(
        self,
        *,
        task_id: str,
        agent_id: str,
        result_path: str,
        extra_outputs: dict[str, Any] | None,
        result_asset: dict[str, Any] | None = None,
        extra_output_assets: dict[str, Any] | None = None,
        attempts: int,
        retry_base_seconds: float,
        retry_max_seconds: float,
        sleep_func,
    ) -> None:
        payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "result": result_path,
            "extra_outputs": extra_outputs or {},
        }
        if result_asset is not None:
            payload["result_asset"] = result_asset
        if extra_output_assets is not None:
            payload["extra_output_assets"] = extra_output_assets
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = await self.master_post(
                    "/api/agent/task/complete",
                    json=payload,
                )
                status_code = getattr(response, "status_code", 200)
                if status_code >= 400:
                    raise RuntimeError(
                        f"Central API returned HTTP {status_code} for completion"
                    )
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    self.logger.error(
                        "Failed to report completion for task %s after %s attempts: %s",
                        task_id,
                        attempts,
                        exc,
                    )
                    raise RuntimeError(
                        f"Failed to report completion for task {task_id}"
                    ) from exc

                delay = min(
                    retry_base_seconds * (2 ** (attempt - 1)),
                    retry_max_seconds,
                )
                self.logger.warning(
                    "Failed to report completion for task %s (attempt %s/%s): %s; retrying in %.1fs",
                    task_id,
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                await sleep_func(delay)

        raise RuntimeError(
            f"Failed to report completion for task {task_id}"
        ) from last_error
