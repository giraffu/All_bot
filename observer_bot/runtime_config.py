from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class ObserverRuntimeConfig:
    admin_chat_ids: frozenset[int]
    authorized_group_ids: frozenset[int]
    queue_alerts_enabled: bool
    queue_total_pending_threshold: int
    queue_type_pending_threshold: int
    group_collection_enabled: bool
    daily_reports_enabled: bool
    weekly_reports_enabled: bool
    monthly_reports_enabled: bool

    def report_enabled(self, report_type: str) -> bool:
        return bool(
            {
                "daily": self.daily_reports_enabled,
                "weekly": self.weekly_reports_enabled,
                "monthly": self.monthly_reports_enabled,
            }.get(report_type, False)
        )


class ObserverRuntimeConfigProvider:
    def __init__(self, repository, *, ttl_seconds: float = 15):
        self._repository = repository
        self._ttl_seconds = ttl_seconds
        self._cached: ObserverRuntimeConfig | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> ObserverRuntimeConfig:
        now = monotonic()
        if self._cached is not None and now < self._expires_at:
            return self._cached
        async with self._lock:
            now = monotonic()
            if self._cached is None or now >= self._expires_at:
                self._cached = await self._repository.get_runtime_config()
                self._expires_at = now + self._ttl_seconds
            return self._cached

    def invalidate(self) -> None:
        self._expires_at = 0.0
