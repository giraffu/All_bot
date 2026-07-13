from __future__ import annotations

from typing import Any


class AgentHealthManager:
    def __init__(self, *, agent: Any, logger) -> None:
        self.agent = agent
        self.logger = logger

    def record_control_plane_success(self) -> None:
        if self.agent.control_plane_failures:
            self.logger.info(
                "Control plane recovered after %s consecutive failed request(s)",
                self.agent.control_plane_failures,
            )
        self.agent.control_plane_failures = 0
        self.agent.control_plane_failure_started_at = None
        self.agent.control_plane_last_error = ""

    def record_control_plane_failure(
        self,
        error: Exception | str,
        *,
        recovery_enabled: bool,
        min_failures: int,
        recovery_seconds: float,
        agent_id: str,
        exit_code: int,
        recovery_exit_cls,
    ) -> None:
        if not recovery_enabled:
            return

        now = self.agent._now()
        if self.agent.control_plane_failure_started_at is None:
            self.agent.control_plane_failure_started_at = now
        self.agent.control_plane_failures += 1
        self.agent.control_plane_last_error = str(error)

        failed_seconds = now - self.agent.control_plane_failure_started_at
        if (
            self.agent.control_plane_failures < min_failures
            or failed_seconds < recovery_seconds
        ):
            return

        self.agent.control_plane_recovery_requested = True
        self.agent.running = False
        self.logger.error(
            "Agent %s control plane recovery threshold reached after %s failure(s) "
            "over %.1fs; exiting with code %s for Docker restart",
            agent_id,
            self.agent.control_plane_failures,
            failed_seconds,
            exit_code,
        )
        raise recovery_exit_cls(self.agent.control_plane_last_error)

    def record_health_failure(
        self,
        *,
        reason: str,
        error: str,
        failure_threshold: int,
        agent_id: str,
    ) -> None:
        self.agent.consecutive_failures += 1
        self.agent.consecutive_successes = 0
        self.agent.health_reason = reason
        self.agent.last_error = error
        self.agent.last_error_at = self.agent._now()
        if self.agent.consecutive_failures >= failure_threshold:
            if not self.agent.is_error_state:
                self.logger.error(
                    "Agent %s reached ComfyUI health failure threshold; marking worker as error",
                    agent_id,
                )
            self.agent.is_error_state = True

    def record_health_success(self, *, recovery_threshold: int) -> None:
        self.agent.consecutive_successes += 1
        if (
            self.agent.is_error_state
            and self.agent.consecutive_successes < recovery_threshold
        ):
            return
        self.agent.consecutive_failures = 0
        self.agent.consecutive_successes = 0
        if self.agent.is_error_state:
            self.logger.info("ComfyUI health recovered; clearing worker error state")
        self.agent.is_error_state = False
        self.agent.health_reason = ""
        self.agent.last_error = ""
        self.agent.last_error_at = None

    def is_quarantined(self) -> bool:
        return (
            self.agent.quarantined_until is not None
            and self.agent.quarantined_until > self.agent._now()
        )

    def clear_expired_quarantine(self) -> bool:
        if self.agent.quarantined_until is None:
            return False
        if self.agent.quarantined_until > self.agent._now():
            return False
        self.logger.info(
            "Worker quarantine expired; health checks may resume task polling"
        )
        self.agent.quarantined_until = None
        self.agent.task_infra_failures = 0
        if self.agent.health_reason == "task_infra_failures":
            self.agent.health_reason = ""
            self.agent.last_error = ""
            self.agent.last_error_at = None
        return True

    def enter_quarantine(
        self,
        *,
        error: str,
        quarantine_seconds: float,
        agent_id: str,
    ) -> None:
        self.agent.quarantined_until = self.agent._now() + quarantine_seconds
        self.agent.health_reason = "task_infra_failures"
        self.agent.last_error = error
        self.agent.last_error_at = self.agent._now()
        self.logger.error(
            "Agent %s entered quarantine for %.0fs after %s consecutive infrastructure failures",
            agent_id,
            quarantine_seconds,
            self.agent.task_infra_failures,
        )

    @staticmethod
    def is_infrastructure_failure(
        error: Exception,
        *,
        user_input_markers: tuple[str, ...],
        infra_error_markers: tuple[str, ...],
    ) -> bool:
        message = str(error).lower()
        if any(marker in message for marker in user_input_markers):
            return False
        return any(marker in message for marker in infra_error_markers)

    def record_task_failure_for_health(
        self,
        error: Exception,
        *,
        user_input_markers: tuple[str, ...],
        infra_error_markers: tuple[str, ...],
        failure_threshold: int,
        quarantine_seconds: float,
        agent_id: str,
    ) -> None:
        if not self.is_infrastructure_failure(
            error,
            user_input_markers=user_input_markers,
            infra_error_markers=infra_error_markers,
        ):
            self.agent.task_infra_failures = 0
            return
        self.agent.task_infra_failures += 1
        if self.agent.task_infra_failures >= failure_threshold:
            self.enter_quarantine(
                error=str(error),
                quarantine_seconds=quarantine_seconds,
                agent_id=agent_id,
            )

    def record_task_success_for_health(self) -> None:
        self.agent.task_infra_failures = 0

    def worker_status(self) -> str:
        if self.is_quarantined():
            return "quarantined"
        if self.agent.is_error_state:
            return "error"
        return (
            "running"
            if self.agent._executions or self.agent._active_execution
            else "idle"
        )

    def heartbeat_health_payload(self) -> dict[str, Any]:
        failure_count = (
            self.agent.task_infra_failures
            if self.is_quarantined()
            else self.agent.consecutive_failures
        )
        return {
            "health_reason": self.agent.health_reason,
            "last_error": self.agent.last_error,
            "last_error_at": self.agent.last_error_at,
            "consecutive_failures": failure_count,
            "quarantined_until": self.agent.quarantined_until,
        }
