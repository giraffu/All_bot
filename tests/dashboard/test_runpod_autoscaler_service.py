from __future__ import annotations

import pytest
from fastapi import HTTPException

from dashboard.backend.services.runpod_admin_operation import RunPodAdminOperation
from dashboard.backend.services.runpod_autoscaler_service import (
    InMemoryRunPodAutoscalerStateStore,
    RunPodAutoscalerConfig,
    evaluate_runpod_autoscaler_once,
    set_runpod_autoscaler_settings_payload,
)

pytestmark = pytest.mark.asyncio


def _config() -> RunPodAutoscalerConfig:
    return RunPodAutoscalerConfig(
        configured_enabled=True,
        cooldown_seconds=600,
        max_runpods_per_profile=5,
        heartbeat_max_age_seconds=300,
        owner_id="test-autoscaler",
    )


def _status(*, profile: str, pending: int, wait: int | None, active: int = 0):
    profiles = [
        "img2img",
        "image_to_video",
        "wan22_video_v2",
        "i2i_pro",
        "scail2",
        "ltx_video",
    ]
    return {
        "runpod_profile_queue_details": [
            {
                "profile": item,
                "label": item,
                "supported_task_types": [item],
                "active_count": active if item == profile else 0,
                "pending_count": pending if item == profile else 0,
                "max_pending_wait_seconds": wait if item == profile else None,
            }
            for item in profiles
        ]
    }


def _workers(*items):
    return {"workers": list(items)}


def _runpod_worker(
    profile: str,
    slot: str,
    *,
    status: str = "idle",
    control_state: str = "enabled",
    last_seen: float = 1000.0,
    current_task_id: str | None = None,
):
    profile_agent = {
        "img2img": "runpod_prod_img2img_manual_",
        "image_to_video": "runpod_prod_image_to_video_manual_",
        "wan22_video_v2": "runpod_prod_wan22_video_v2_manual_",
        "i2i_pro": "runpod_prod_i2i_pro_manual_",
        "scail2": "runpod_prod_scail2_manual_",
        "ltx_video": "runpod_prod_ltx_video_manual_",
    }
    profile_types = {
        "img2img": "img2img,img2img_lora",
        "image_to_video": "image_to_video",
        "wan22_video_v2": "wan22_video_v2",
        "i2i_pro": "i2i_pro,t2i-pornmaster-turbo,face_swap",
        "scail2": "scail2_action_transfer,scail2_video_replacement",
        "ltx_video": "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio",
    }
    return {
        "agent_id": f"{profile_agent[profile]}{slot}",
        "provider": "runpod",
        "runtime_profile": profile,
        "types": profile_types[profile],
        "status": status,
        "control_state": control_state,
        "last_seen": last_seen,
        "current_task_id": current_task_id,
    }


def _local_worker(
    task_types: str,
    *,
    status: str = "idle",
    control_state: str = "enabled",
    last_seen: float = 1000.0,
):
    return {
        "agent_id": f"local_{task_types.replace(',', '_')}",
        "provider": "lan_ssh",
        "types": task_types,
        "status": status,
        "control_state": control_state,
        "last_seen": last_seen,
    }


async def _empty_operations():
    return {"operations": []}


def _finished_autoscaler_operation(profile: str, *, ended_at: str):
    return {
        "id": f"{profile}-finished",
        "profile": profile,
        "action": "add",
        "status": "succeeded",
        "source": "autoscaler",
        "ended_at": ended_at,
    }


def _active_operation(profile: str, *, action: str = "add"):
    return {
        "id": f"{profile}-active",
        "profile": profile,
        "action": action,
        "status": "running",
        "source": "autoscaler",
    }


async def test_autoscaler_scales_up_when_wait_exceeds_threshold():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-add",
            action="add",
            profile=kwargs["profile"],
            command=["runpod", "add"],
            source="autoscaler",
            trigger_reason=kwargs["trigger_reason"],
        )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="img2img", pending=1, wait=1801),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    assert calls[0]["profile"] == "img2img"
    assert payload["decisions"][0]["action"] == "scale_up"
    assert payload["executed_operations"][0]["source"] == "autoscaler"


async def test_autoscaler_uses_default_profile_scale_up_thresholds():
    config = _config()
    payload = await evaluate_runpod_autoscaler_once(
        mutate=False,
        config=config,
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="scail2", pending=1, wait=1900),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        now_func=lambda: 1000.0,
    )

    decisions = {item["profile"]: item for item in payload["decisions"]}
    thresholds = payload["config"]["scale_up_wait_seconds_by_profile"]
    assert thresholds["img2img"] == 20 * 60
    assert thresholds["scail2"] == 40 * 60
    assert thresholds["image_to_video"] == 30 * 60
    assert decisions["scail2"]["action"] == "hold"
    assert decisions["scail2"]["scale_up_wait_seconds"] == 40 * 60
    assert decisions["scail2"]["reason"] == "within thresholds"


async def test_autoscaler_uses_persisted_profile_scale_up_threshold_on_next_evaluate():
    store = InMemoryRunPodAutoscalerStateStore()
    await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile={"scail2": 31},
        reason="test threshold update",
        store=store,
        refresh_payload=False,
    )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=False,
        config=_config(),
        store=store,
        status_payload=_status(profile="scail2", pending=1, wait=1900),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["scail2"]
    assert payload["config"]["scale_up_wait_seconds_by_profile"]["scail2"] == 31 * 60
    assert decision["action"] == "scale_up"
    assert decision["scale_up_wait_seconds"] == 31 * 60
    assert decision["reason"] == "pending wait 1900s exceeds 1860s"


@pytest.mark.parametrize(
    "updates",
    [
        {"unknown": 30},
        {"img2img": 0},
        {"img2img": 241},
    ],
)
async def test_autoscaler_rejects_invalid_profile_scale_up_threshold_settings(updates):
    with pytest.raises(HTTPException) as exc_info:
        await set_runpod_autoscaler_settings_payload(
            scale_up_wait_minutes_by_profile=updates,
            store=InMemoryRunPodAutoscalerStateStore(),
        )

    assert exc_info.value.status_code == 422


async def test_autoscaler_does_not_duplicate_active_or_cooling_profile_operations():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="img2img", pending=1, wait=2400),
        workers_payload=_workers(),
        operations_payload={
            "operations": [
                _active_operation("img2img"),
                _finished_autoscaler_operation(
                    "image_to_video",
                    ended_at="1970-01-01T00:15:00Z",
                ),
            ]
        },
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decisions = {item["profile"]: item for item in payload["decisions"]}
    assert decisions["img2img"]["action"] == "hold"
    assert "operation active" in decisions["img2img"]["reason"]
    assert decisions["image_to_video"]["action"] == "hold"
    assert "cooldown" in decisions["image_to_video"]["reason"]
    assert calls == []


async def test_autoscaler_holds_when_profile_reaches_runpod_limit():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="img2img", pending=2, wait=2400),
        workers_payload=_workers(
            *[_runpod_worker("img2img", f"{index:02d}") for index in range(1, 6)]
        ),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = payload["decisions"][0]
    assert decision["action"] == "hold"
    assert decision["reason"] == "max runpod capacity reached"
    assert calls == []


async def test_autoscaler_scales_down_idle_runpod_when_local_capacity_remains():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-delete",
            action="delete",
            profile=kwargs["profile"],
            command=["runpod", "down"],
            slot=kwargs["slot"],
            source="autoscaler",
            trigger_reason=kwargs["trigger_reason"],
        )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="i2i_pro", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("i2i_pro", "01"),
            _local_worker("i2i_pro,t2i-pornmaster-turbo,face_swap"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "scale_down"
    assert calls == [
        {
            "profile": "i2i_pro",
            "slot": "01",
            "trigger_reason": "pending wait below scale-down threshold",
            "spawn_task_func": None,
        }
    ]


async def test_autoscaler_does_not_scale_down_below_one_total_accepting_worker():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not delete")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="wan22_video_v2", pending=0, wait=None),
        workers_payload=_workers(_runpod_worker("wan22_video_v2", "01")),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "wan22_video_v2"
    ]
    assert decision["action"] == "hold"
    assert decision["reason"] == "minimum total accepting capacity reached"
    assert calls == []


async def test_autoscaler_ignores_disabled_and_unhealthy_workers_for_capacity():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not delete")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="ltx_video", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("ltx_video", "01"),
            _local_worker("ltx_video", control_state="disabled"),
            _local_worker("ltx_video_flf2v", status="error"),
            _local_worker("ltx_video_v2v_audio", status="quarantined"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "ltx_video"
    ]
    assert decision["total_accepting_count"] == 1
    assert decision["action"] == "hold"
    assert calls == []


async def test_autoscaler_does_not_scale_down_without_idle_runpod_candidate():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not delete")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="scail2", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("scail2", "01", status="running", current_task_id="task-1"),
            _local_worker("scail2_action_transfer"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["scail2"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "no idle runpod candidate"
    assert calls == []


async def test_autoscaler_requires_leader_lease_before_mutation():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(leader_available=False),
        status_payload=_status(profile="img2img", pending=1, wait=2400),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    assert payload["leader_acquired"] is False
    assert payload["mutation_skipped_reason"] == "leader lease not acquired"
    assert calls == []
