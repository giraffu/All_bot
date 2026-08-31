from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from observer_bot.domain import parse_datetime


class StateRepository(Protocol):
    async def get_state(self, key: str) -> dict[str, Any]: ...

    async def set_state(self, key: str, value: dict[str, Any]) -> None: ...


class AdminNotifier(Protocol):
    async def send_admins(self, text: str) -> None: ...


@dataclass(frozen=True)
class WorkerOutcomeStats:
    worker_id: str
    status: str
    total_tasks: int
    failed_tasks: int
    failure_rate: float
    failures_by_type: dict[str, int]
    last_failure_at: float | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WorkerOutcomeStats":
        failures_by_type = payload.get("failures_by_type") or {}
        return cls(
            worker_id=str(payload.get("worker_id") or "unknown"),
            status=str(payload.get("status") or "unknown"),
            total_tasks=int(payload.get("total_tasks") or 0),
            failed_tasks=int(payload.get("failed_tasks") or 0),
            failure_rate=float(payload.get("failure_rate") or 0.0),
            failures_by_type={
                str(task_type): int(count or 0)
                for task_type, count in failures_by_type.items()
            },
            last_failure_at=(
                float(payload["last_failure_at"])
                if payload.get("last_failure_at") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class WorkerOutcomeSnapshot:
    window_seconds: int
    workers: tuple[WorkerOutcomeStats, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "WorkerOutcomeSnapshot":
        return cls(
            window_seconds=int(payload.get("window_seconds") or 3600),
            workers=tuple(
                WorkerOutcomeStats.from_payload(item)
                for item in (payload.get("workers") or [])
                if isinstance(item, dict)
            ),
        )


class WorkerErrorProbe:
    _STATE_KEY = "worker_error_probe"
    _POLICY = "failure_rate_v1"

    def __init__(
        self,
        *,
        client,
        state_repository: StateRepository,
        notifier: AdminNotifier,
        cooldown_seconds: int,
        failure_threshold: int,
    ):
        self._client = client
        self._repository = state_repository
        self._notifier = notifier
        self._cooldown_seconds = cooldown_seconds
        self._failure_threshold = failure_threshold

    async def poll(
        self,
        *,
        window_seconds: int,
        minimum_tasks: int,
        minimum_failures: int,
        failure_rate_threshold: float,
        now: datetime | None = None,
    ) -> WorkerOutcomeSnapshot | None:
        observed_at = now or datetime.now(timezone.utc)
        state = await self._repository.get_state(self._STATE_KEY)
        try:
            snapshot = await self._client.fetch_worker_outcomes(
                window_seconds=window_seconds
            )
        except Exception:
            await self._record_failure(state, observed_at)
            return None

        if int(state.get("consecutive_failures") or 0) >= self._failure_threshold:
            await self._notifier.send_admins(
                "✅ AllBot Worker 失败率探针恢复，已重新取得 Central 统计。"
            )
        state["consecutive_failures"] = 0
        previous_workers = state.get("workers") or {}
        current_workers: dict[str, dict[str, Any]] = {}

        for worker in snapshot.workers:
            previous = previous_workers.get(worker.worker_id) or {}
            was_alerting = bool(
                previous.get("policy") == self._POLICY and previous.get("alerting")
            )
            is_alerting = bool(
                worker.total_tasks >= minimum_tasks
                and worker.failed_tasks >= minimum_failures
                and worker.failure_rate >= failure_rate_threshold
            )
            last_notification = parse_datetime(previous.get("last_notification_at"))
            reminder_due = bool(
                is_alerting
                and was_alerting
                and (
                    last_notification is None
                    or (observed_at - last_notification).total_seconds()
                    >= self._cooldown_seconds
                )
            )
            next_worker_state = {
                "policy": self._POLICY,
                "alerting": is_alerting,
                "last_observed_at": observed_at.isoformat(),
            }

            if is_alerting and (not was_alerting or reminder_due):
                label = "失败率过高" if not was_alerting else "失败率仍然过高"
                await self._notifier.send_admins(
                    self._alert_text(
                        worker,
                        label=label,
                        window_seconds=window_seconds,
                    )
                )
                next_worker_state["last_notification_at"] = observed_at.isoformat()
            elif was_alerting and not is_alerting:
                await self._notifier.send_admins(
                    "✅ AllBot Worker 失败率恢复"
                    f"\n• Worker: {worker.worker_id}"
                    f"\n• 当前窗口: {worker.failed_tasks}/{worker.total_tasks}"
                    f"（{worker.failure_rate:.1%}）"
                )
                next_worker_state["last_notification_at"] = observed_at.isoformat()
            elif previous.get("last_notification_at"):
                next_worker_state["last_notification_at"] = previous[
                    "last_notification_at"
                ]

            current_workers[worker.worker_id] = next_worker_state

        state["workers"] = current_workers
        state["last_observed_at"] = observed_at.isoformat()
        await self._repository.set_state(self._STATE_KEY, state)
        return snapshot

    async def _record_failure(self, state: dict[str, Any], now: datetime) -> None:
        failures = int(state.get("consecutive_failures") or 0) + 1
        state["consecutive_failures"] = failures
        if failures == self._failure_threshold:
            await self._notifier.send_admins(
                f"⚠️ AllBot Worker 失败率探针不可用：连续 {failures} 次无法读取 Central 统计。"
            )
        state["last_failure_at"] = now.isoformat()
        await self._repository.set_state(self._STATE_KEY, state)

    @staticmethod
    def _alert_text(
        worker: WorkerOutcomeStats,
        *,
        label: str,
        window_seconds: int,
    ) -> str:
        task_types = sorted(
            worker.failures_by_type.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
        type_summary = (
            "、".join(f"{task_type}: {count}" for task_type, count in task_types)
            or "unknown"
        )
        return (
            f"🚨 AllBot Worker {label}"
            f"\n• Worker: {worker.worker_id}"
            f"\n• 状态: {worker.status}"
            f"\n• 最近 {max(1, window_seconds // 60)} 分钟: "
            f"{worker.failed_tasks}/{worker.total_tasks}（{worker.failure_rate:.1%}）"
            f"\n• 失败任务类型: {type_summary}"
        )
