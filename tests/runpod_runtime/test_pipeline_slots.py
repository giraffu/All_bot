import asyncio

import pytest

from workers.comfy_agent.pipeline_slots import (
    FAST_IMAGE_PIPELINE_POLICY,
    MEDIA_PIPELINE_POLICY,
    PipelineAdmission,
    PipelineDeliveryGate,
    resolve_pipeline_limits,
)
from workers.comfy_agent.agent_runtime_types import TaskExecutionContext


def _execution(task_id: str, phase: str) -> TaskExecutionContext:
    return TaskExecutionContext(
        task_id=task_id,
        task_type="pornmaster_flux2_edit_bf16",
        phase=phase,
    )


def test_profile_policies_resolve_bounded_image_and_media_limits():
    assert resolve_pipeline_limits(
        policy=FAST_IMAGE_PIPELINE_POLICY,
        max_running_tasks=1,
        max_claimed_tasks=2,
        delivery_concurrency=1,
    ) == (2, 3, 1)

    assert resolve_pipeline_limits(
        policy=MEDIA_PIPELINE_POLICY,
        max_running_tasks=1,
        max_claimed_tasks=2,
        delivery_concurrency=1,
    ) == (1, 2, 1)

    assert resolve_pipeline_limits(
        policy="",
        max_running_tasks=1,
        max_claimed_tasks=2,
        delivery_concurrency=1,
    ) == (1, 2, 1)


def test_pipeline_admission_caps_claims_and_promotes_reserved_task():
    admission = PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )
    executions = {
        "delivery": _execution("delivery", "delivering"),
        "gpu": _execution("gpu", "running"),
    }
    reserved = {"task_id": "reserved"}

    assert admission.claimed_count(executions, reserved) == 3
    assert admission.comfy_inflight_count(executions) == 1
    assert admission.can_take_task(executions, reserved)
    assert not admission.can_reserve_task(executions, reserved)

    executions["queued"] = _execution("queued", "queued")
    assert admission.comfy_inflight_count(executions) == 2
    assert not admission.can_take_task(executions, None)


def test_pipeline_admission_blocks_new_claim_at_limit_without_reserved_task():
    admission = PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )
    executions = {
        "delivery-a": _execution("delivery-a", "delivering"),
        "delivery-b": _execution("delivery-b", "gpu_done"),
        "gpu": _execution("gpu", "running"),
    }

    assert admission.claimed_count(executions, None) == 3
    assert not admission.can_take_task(executions, None)
    assert not admission.can_reserve_task(executions, None)


@pytest.mark.asyncio
async def test_delivery_gate_serializes_uploads():
    gate = PipelineDeliveryGate(concurrency=1)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first():
        async with gate.slot():
            first_entered.set()
            await release_first.wait()

    async def second():
        await first_entered.wait()
        async with gate.slot():
            second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_entered.wait()
    await asyncio.sleep(0)

    assert gate.active == 1
    assert not second_entered.is_set()

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert second_entered.is_set()
    assert gate.active == 0
    assert gate.max_observed == 1
