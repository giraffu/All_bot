from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Mapping


POST_COMFY_PHASES = frozenset(
    {
        "gpu_done",
        "delivering",
        "reporting_complete",
    }
)

FAST_IMAGE_PIPELINE_POLICY = "image_claim3_comfy2_delivery1_v1"
MEDIA_PIPELINE_POLICY = "media_claim2_comfy1_delivery1_v1"
LEGACY_BF16_LAN_PIPELINE_POLICY = "bf16_lan_claim3_comfy2_delivery1"
# Import compatibility for tests and older code that named the pilot policy.
BF16_LAN_PIPELINE_POLICY = LEGACY_BF16_LAN_PIPELINE_POLICY


def resolve_pipeline_limits(
    *,
    policy: str,
    max_running_tasks: int,
    max_claimed_tasks: int,
    delivery_concurrency: int,
) -> tuple[int, int, int]:
    normalized_policy = policy.strip()
    if normalized_policy in {
        FAST_IMAGE_PIPELINE_POLICY,
        LEGACY_BF16_LAN_PIPELINE_POLICY,
    }:
        return 2, 3, 1
    if normalized_policy == MEDIA_PIPELINE_POLICY:
        return 1, 2, 1
    normalized_running = max(1, int(max_running_tasks))
    return (
        normalized_running,
        max(normalized_running, int(max_claimed_tasks)),
        max(1, int(delivery_concurrency)),
    )


class PipelineAdmission:
    def __init__(self, *, max_claimed_tasks: int, max_comfy_inflight: int) -> None:
        self.max_claimed_tasks = max(1, int(max_claimed_tasks))
        self.max_comfy_inflight = max(1, int(max_comfy_inflight))
        if self.max_comfy_inflight > self.max_claimed_tasks:
            raise ValueError("max_comfy_inflight must not exceed max_claimed_tasks")

    @staticmethod
    def claimed_count(
        executions: Mapping[str, Any],
        reserved_task: Mapping[str, Any] | None,
    ) -> int:
        return len(executions) + (1 if reserved_task else 0)

    @staticmethod
    def comfy_inflight_count(executions: Mapping[str, Any]) -> int:
        return sum(
            1
            for execution in executions.values()
            if str(getattr(execution, "phase", "")) not in POST_COMFY_PHASES
        )

    def can_take_task(
        self,
        executions: Mapping[str, Any],
        reserved_task: Mapping[str, Any] | None,
    ) -> bool:
        if self.comfy_inflight_count(executions) >= self.max_comfy_inflight:
            return False
        if reserved_task:
            return True
        return self.claimed_count(executions, None) < self.max_claimed_tasks

    def can_reserve_task(
        self,
        executions: Mapping[str, Any],
        reserved_task: Mapping[str, Any] | None,
    ) -> bool:
        if reserved_task:
            return False
        return self.claimed_count(executions, None) < self.max_claimed_tasks


class PipelineDeliveryGate:
    def __init__(self, *, concurrency: int) -> None:
        self.concurrency = max(1, int(concurrency))
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self.active = 0
        self.max_observed = 0

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._semaphore:
            self.active += 1
            self.max_observed = max(self.max_observed, self.active)
            try:
                yield
            finally:
                self.active -= 1
