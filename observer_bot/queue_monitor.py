from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx


class StateRepository(Protocol):
    async def get_state(self, key: str) -> dict[str, Any]: ...

    async def set_state(self, key: str, value: dict[str, Any]) -> None: ...


class AdminNotifier(Protocol):
    async def send_admins(self, text: str) -> None: ...


@dataclass(frozen=True)
class QueueSnapshot:
    queue_size: int
    accepting_workers: int
    max_wait_seconds: int
    pending_by_type: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "QueueSnapshot":
        details = payload.get("queue_by_type_details") or {}
        waits = [
            int(float(item.get("max_pending_wait_seconds") or 0))
            for item in details.values()
            if isinstance(item, dict)
        ]
        pending_by_type = {
            str(task_type): int(float(item.get("pending_count") or 0))
            for task_type, item in details.items()
            if isinstance(item, dict)
        }
        return cls(
            queue_size=int(payload.get("queue_size") or 0),
            accepting_workers=int(payload.get("accepting_workers") or 0),
            max_wait_seconds=max(waits, default=0),
            pending_by_type=pending_by_type,
        )


class CentralQueueClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 12):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def fetch(self) -> QueueSnapshot:
        response = await self._client.get(f"{self._base_url}/system/status")
        response.raise_for_status()
        return QueueSnapshot.from_payload(response.json())

    async def close(self) -> None:
        await self._client.aclose()


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class QueueMonitor:
    _STATE_KEY = "queue_monitor"
    _CONGESTION_POLICY = "count_thresholds_v1"

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
        total_pending_threshold: int,
        type_pending_threshold: int,
        now: datetime | None = None,
    ) -> QueueSnapshot | None:
        observed_at = now or datetime.now(timezone.utc)
        state = await self._repository.get_state(self._STATE_KEY)
        try:
            snapshot = await self._client.fetch()
        except Exception:
            await self._record_failure(state, observed_at)
            return None

        if int(state.get("consecutive_failures") or 0) >= self._failure_threshold:
            await self._notifier.send_admins(
                "✅ AllBot 队列监控恢复，已重新取得 Central 状态。"
            )
        state["consecutive_failures"] = 0
        await self._handle_snapshot(
            snapshot,
            state,
            observed_at,
            total_pending_threshold=max(1, int(total_pending_threshold)),
            type_pending_threshold=max(1, int(type_pending_threshold)),
        )
        await self._repository.set_state(self._STATE_KEY, state)
        return snapshot

    async def _record_failure(self, state: dict[str, Any], now: datetime) -> None:
        failures = int(state.get("consecutive_failures") or 0) + 1
        state["consecutive_failures"] = failures
        if failures == self._failure_threshold:
            await self._notifier.send_admins(
                f"⚠️ AllBot 队列监控不可用：连续 {failures} 次无法读取 Central 状态。"
            )
        await self._repository.set_state(self._STATE_KEY, state)

    async def _handle_snapshot(
        self,
        snapshot: QueueSnapshot,
        state: dict[str, Any],
        now: datetime,
        *,
        total_pending_threshold: int,
        type_pending_threshold: int,
    ) -> None:
        reasons: list[str] = []
        if snapshot.queue_size > total_pending_threshold:
            reasons.append(
                f"待处理 {snapshot.queue_size}（总量阈值 {total_pending_threshold}）"
            )
        congested_types = sorted(
            (
                (task_type, pending_count)
                for task_type, pending_count in snapshot.pending_by_type.items()
                if pending_count > type_pending_threshold
            ),
            key=lambda item: (-item[1], item[0]),
        )
        reasons.extend(
            f"{task_type} 待处理 {pending_count}（单类型阈值 {type_pending_threshold}）"
            for task_type, pending_count in congested_types
        )
        was_congested = bool(
            state.get("congestion_policy") == self._CONGESTION_POLICY
            and state.get("congested")
        )
        is_congested = bool(reasons)
        last_notification = _parse_time(state.get("last_notification_at"))
        reminder_due = bool(
            is_congested
            and was_congested
            and (
                last_notification is None
                or (now - last_notification).total_seconds() >= self._cooldown_seconds
            )
        )

        if is_congested and (not was_congested or reminder_due):
            label = "队列拥堵" if not was_congested else "队列仍拥堵"
            await self._notifier.send_admins(
                f"🚨 AllBot {label}\n" + "\n".join(f"• {reason}" for reason in reasons)
            )
            state["last_notification_at"] = now.isoformat()
        elif was_congested and not is_congested:
            await self._notifier.send_admins(
                "✅ AllBot 队列恢复"
                f"\n• 待处理 {snapshot.queue_size}"
                f"\n• 可接单 Worker {snapshot.accepting_workers}"
            )
            state["last_notification_at"] = now.isoformat()

        state["congested"] = is_congested
        state["congestion_policy"] = self._CONGESTION_POLICY
        state["last_queue_size"] = snapshot.queue_size
        state["last_accepting_workers"] = snapshot.accepting_workers
        state["last_max_wait_seconds"] = snapshot.max_wait_seconds
        state["last_pending_by_type"] = snapshot.pending_by_type
        state["last_observed_at"] = now.isoformat()
