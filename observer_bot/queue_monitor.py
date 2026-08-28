from __future__ import annotations

from dataclasses import dataclass
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

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "QueueSnapshot":
        details = payload.get("queue_by_type_details") or {}
        waits = [
            int(float(item.get("max_pending_wait_seconds") or 0))
            for item in details.values()
            if isinstance(item, dict)
        ]
        return cls(
            queue_size=int(payload.get("queue_size") or 0),
            accepting_workers=int(payload.get("accepting_workers") or 0),
            max_wait_seconds=max(waits, default=0),
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

    def __init__(
        self,
        *,
        client,
        state_repository: StateRepository,
        notifier: AdminNotifier,
        queue_size_threshold: int,
        wait_threshold_seconds: int,
        cooldown_seconds: int,
        failure_threshold: int,
    ):
        self._client = client
        self._repository = state_repository
        self._notifier = notifier
        self._queue_size_threshold = queue_size_threshold
        self._wait_threshold_seconds = wait_threshold_seconds
        self._cooldown_seconds = cooldown_seconds
        self._failure_threshold = failure_threshold

    async def poll(self, *, now: datetime | None = None) -> QueueSnapshot | None:
        observed_at = now or datetime.now(timezone.utc)
        state = await self._repository.get_state(self._STATE_KEY)
        try:
            snapshot = await self._client.fetch()
        except Exception:
            await self._record_failure(state, observed_at)
            return None

        if int(state.get("consecutive_failures") or 0) >= self._failure_threshold:
            await self._notifier.send_admins("✅ AllBot 队列监控恢复，已重新取得 Central 状态。")
        state["consecutive_failures"] = 0
        await self._handle_snapshot(snapshot, state, observed_at)
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
    ) -> None:
        reasons: list[str] = []
        if snapshot.queue_size >= self._queue_size_threshold:
            reasons.append(
                f"待处理 {snapshot.queue_size}（阈值 {self._queue_size_threshold}）"
            )
        if snapshot.max_wait_seconds >= self._wait_threshold_seconds:
            reasons.append(
                f"最长等待 {snapshot.max_wait_seconds} 秒（阈值 {self._wait_threshold_seconds} 秒）"
            )
        if snapshot.queue_size > 0 and snapshot.accepting_workers == 0:
            reasons.append("有排队任务但没有可接单 Worker")

        was_congested = bool(state.get("congested"))
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
        state["last_queue_size"] = snapshot.queue_size
        state["last_accepting_workers"] = snapshot.accepting_workers
        state["last_max_wait_seconds"] = snapshot.max_wait_seconds
        state["last_observed_at"] = now.isoformat()
