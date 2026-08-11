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


def _config(*, min_runpod_lifetime_seconds: int = 0) -> RunPodAutoscalerConfig:
    return RunPodAutoscalerConfig(
        configured_enabled=True,
        cooldown_seconds=600,
        max_runpods_per_profile=5,
        heartbeat_max_age_seconds=300,
        owner_id="test-autoscaler",
        min_runpod_lifetime_seconds=min_runpod_lifetime_seconds,
        runpod_bootstrap_timeout_seconds=2400,
        runpod_bootstrap_replacement_limit=2,
        runpod_bootstrap_replacement_window_seconds=7200,
    )


def _status(
    *,
    profile: str,
    pending: int,
    wait: int | None,
    active: int = 0,
    priority: int = 1,
    pending_wait_records: list[dict] | None = None,
    pending_count_by_task_type: dict[str, int] | None = None,
    non_low_trust_clear_pending_count_by_task_type: dict[str, int] | None = None,
):
    profiles = [
        "img2img",
        "image_to_video",
        "wan22_video_v2",
        "i2i_pro",
        "scail2",
        "ltx_video",
        "pornmaster_flux2_edit",
        "pornmaster_flux2_edit_bf16",
    ]
    profile_task_types = {
        "img2img": ["img2img", "img2img_lora"],
        "image_to_video": ["image_to_video"],
        "wan22_video_v2": ["wan22_video_v2"],
        "i2i_pro": [
            "i2i_pro",
            "t2i-pornmaster-turbo",
            "face_swap_v2",
            "face_swap",
        ],
        "scail2": ["scail2_action_transfer", "scail2_video_replacement"],
        "ltx_video": ["ltx_video", "ltx_video_flf2v", "ltx_video_v2v_audio"],
        "pornmaster_flux2_edit": [
            "pornmaster_flux2_single_edit",
            "pornmaster_flux2_multi_edit",
        ],
        "pornmaster_flux2_edit_bf16": [
            "pornmaster_flux2_edit_bf16",
            "pornmaster_flux2_multi_edit_bf16",
        ],
    }
    return {
        "runpod_profile_queue_details": [
            {
                "profile": item,
                "label": item,
                "supported_task_types": profile_task_types[item],
                "active_count": active if item == profile else 0,
                "pending_count": pending if item == profile else 0,
                "pending_count_by_task_type": (
                    pending_count_by_task_type
                    if item == profile and pending_count_by_task_type is not None
                    else (
                        {profile_task_types[item][0]: pending}
                        if item == profile and pending > 0
                        else {}
                    )
                ),
                "non_low_trust_clear_pending_count": (
                    sum(
                        (
                            non_low_trust_clear_pending_count_by_task_type
                            if non_low_trust_clear_pending_count_by_task_type
                            is not None
                            else (
                                pending_count_by_task_type
                                if pending_count_by_task_type is not None
                                else (
                                    {profile_task_types[item][0]: pending}
                                    if pending > 0
                                    else {}
                                )
                            )
                        ).values()
                    )
                    if item == profile
                    else 0
                ),
                "non_low_trust_clear_pending_count_by_task_type": (
                    non_low_trust_clear_pending_count_by_task_type
                    if item == profile
                    and non_low_trust_clear_pending_count_by_task_type is not None
                    else (
                        pending_count_by_task_type
                        if item == profile and pending_count_by_task_type is not None
                        else (
                            {profile_task_types[item][0]: pending}
                            if item == profile and pending > 0
                            else {}
                        )
                    )
                ),
                "max_pending_wait_seconds": wait if item == profile else None,
                "pending_wait_records": (
                    (
                        pending_wait_records
                        if pending_wait_records is not None
                        else [{"wait_seconds": wait, "priority": priority}]
                    )
                    if item == profile and pending > 0 and wait is not None
                    else []
                ),
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
    runpod_locked: bool = False,
    last_seen: float = 1000.0,
    current_task_id: str | None = None,
    current_task_type: str | None = None,
    current_task_created_at: float | None = None,
    last_error_at: float | None = None,
):
    profile_agent = {
        "img2img": "runpod_prod_img2img_manual_",
        "image_to_video": "runpod_prod_image_to_video_manual_",
        "wan22_video_v2": "runpod_prod_wan22_video_v2_manual_",
        "i2i_pro": "runpod_prod_i2i_pro_manual_",
        "scail2": "runpod_prod_scail2_manual_",
        "ltx_video": "runpod_prod_ltx_video_manual_",
        "pornmaster_flux2_edit": "runpod_prod_pornmaster_flux2_edit_manual_",
        "pornmaster_flux2_edit_bf16": (
            "runpod_prod_pornmaster_flux2_edit_bf16_manual_"
        ),
    }
    profile_types = {
        "img2img": "img2img,img2img_lora",
        "image_to_video": "image_to_video",
        "wan22_video_v2": "wan22_video_v2",
        "i2i_pro": "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap",
        "scail2": "scail2_action_transfer,scail2_video_replacement",
        "ltx_video": "ltx_video,ltx_video_flf2v,ltx_video_v2v_audio",
        "pornmaster_flux2_edit": (
            "pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit"
        ),
        "pornmaster_flux2_edit_bf16": (
            "pornmaster_flux2_edit_bf16,pornmaster_flux2_multi_edit_bf16"
        ),
    }
    return {
        "agent_id": f"{profile_agent[profile]}{slot}",
        "provider": "runpod",
        "runtime_profile": profile,
        "types": profile_types[profile],
        "status": status,
        "control_state": control_state,
        "runpod_locked": runpod_locked,
        "last_seen": last_seen,
        "current_task_id": current_task_id,
        "current_task_type": current_task_type,
        "current_task_created_at": current_task_created_at,
        "last_error_at": last_error_at,
    }


def _local_worker(
    task_types: str,
    *,
    status: str = "idle",
    control_state: str = "enabled",
    last_seen: float = 1000.0,
    current_task_type: str | None = None,
    current_task_created_at: float | None = None,
):
    return {
        "agent_id": f"local_{task_types.replace(',', '_')}",
        "provider": "lan_ssh",
        "types": task_types,
        "status": status,
        "control_state": control_state,
        "last_seen": last_seen,
        "current_task_type": current_task_type,
        "current_task_created_at": current_task_created_at,
    }


async def _empty_operations():
    return {"operations": []}


def _finished_autoscaler_operation(
    profile: str,
    *,
    ended_at: str,
    cleanup_slots: list[str] | None = None,
):
    return {
        "id": f"{profile}-finished",
        "profile": profile,
        "action": "add",
        "status": "succeeded",
        "source": "autoscaler",
        "ended_at": ended_at,
        "cleanup_slots": cleanup_slots or [],
    }


def _failed_bootstrap_operation(
    profile: str,
    *,
    ended_at: str,
    slot: str,
    operation_id: str | None = None,
):
    return {
        "id": operation_id or f"{profile}-failed-bootstrap-{slot}",
        "profile": profile,
        "action": "add",
        "status": "failed",
        "source": "autoscaler",
        "ended_at": ended_at,
        "cleanup_slots": [slot],
        "cleanup_status": "succeeded",
        "error": "runpod operation exited with code 1",
    }


def _active_operation(
    profile: str,
    *,
    action: str = "add",
    started_at: str | None = None,
    cleanup_slots: list[str] | None = None,
):
    return {
        "id": f"{profile}-active",
        "profile": profile,
        "action": action,
        "status": "running",
        "source": "autoscaler",
        "started_at": started_at,
        "cleanup_slots": cleanup_slots or [],
    }


async def test_autoscaler_scales_up_when_estimated_clear_time_exceeds_threshold():
    calls = []
    store = InMemoryRunPodAutoscalerStateStore()

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
        store=store,
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    assert calls[0]["profile"] == "img2img"
    decision = payload["decisions"][0]
    assert decision["action"] == "scale_up"
    assert (
        decision["reason"]
        == "scale_up: estimated non-low-trust clear time 1300s exceeds 1200s"
    )
    assert decision["estimated_pending_work_seconds"] == 1300
    assert decision["estimated_non_low_trust_pending_work_seconds"] == 1300
    assert decision["estimated_total_pending_work_seconds"] == 1300
    assert decision["estimated_clear_time_seconds"] == 1300
    assert decision["estimated_non_low_trust_clear_time_seconds"] == 1300
    assert payload["executed_operations"][0]["source"] == "autoscaler"


async def test_autoscaler_holds_long_wait_single_task_when_clear_time_is_low():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(
            profile="img2img",
            pending=1,
            wait=2400,
            pending_wait_records=[
                {"wait_seconds": 2400, "priority": 0},
            ],
        ),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = payload["decisions"][0]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: estimated non-low-trust clear time within threshold"
    assert decision["estimated_clear_time_seconds"] == 13
    assert calls == []


async def test_autoscaler_holds_when_only_low_trust_backlog_exists():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(
            profile="img2img",
            pending=100,
            wait=2400,
            non_low_trust_clear_pending_count_by_task_type={},
        ),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = payload["decisions"][0]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: no non-low-trust backlog"
    assert decision["non_low_trust_clear_pending_count"] == 0
    assert decision["estimated_total_pending_work_seconds"] == 1300
    assert decision["estimated_clear_time_seconds"] is None
    assert calls == []


async def test_autoscaler_uses_default_profile_scale_up_thresholds():
    config = _config()
    payload = await evaluate_runpod_autoscaler_once(
        mutate=False,
        config=config,
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="scail2", pending=1, wait=1900),
        workers_payload=_workers(_local_worker("scail2_action_transfer")),
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
    assert decisions["scail2"]["clear_time_threshold_seconds"] == 40 * 60
    assert (
        decisions["scail2"]["reason"]
        == "hold: estimated non-low-trust clear time within threshold"
    )


async def test_autoscaler_scales_pornmaster_flux2_edit_bf16_profile():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-add-pornmaster-bf16",
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
        status_payload=_status(
            profile="pornmaster_flux2_edit_bf16",
            pending=61,
            wait=1800,
            pending_count_by_task_type={
                "pornmaster_flux2_edit_bf16": 1,
                "pornmaster_flux2_multi_edit_bf16": 60,
            },
        ),
        workers_payload=_workers(_local_worker("pornmaster_flux2_edit_bf16")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "pornmaster_flux2_edit_bf16"
    ]
    assert payload["config"]["scale_up_wait_seconds_by_profile"][
        "pornmaster_flux2_edit_bf16"
    ] == 30 * 60
    assert payload["config"]["task_duration_seconds_by_type"][
        "pornmaster_flux2_edit_bf16"
    ] == 30
    assert payload["config"]["task_duration_seconds_by_type"][
        "pornmaster_flux2_multi_edit_bf16"
    ] == 30
    assert decision["action"] == "scale_up"
    assert decision["estimated_clear_time_seconds"] == 1830
    assert calls[0]["profile"] == "pornmaster_flux2_edit_bf16"


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
        status_payload=_status(profile="scail2", pending=7, wait=10),
        workers_payload=_workers(_local_worker("scail2_action_transfer")),
        operations_payload={"operations": []},
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["scail2"]
    assert payload["config"]["scale_up_wait_seconds_by_profile"]["scail2"] == 31 * 60
    assert decision["action"] == "scale_up"
    assert decision["scale_up_wait_seconds"] == 31 * 60
    assert decision["estimated_clear_time_seconds"] == 2100
    assert (
        decision["reason"]
        == "scale_up: estimated non-low-trust clear time 2100s exceeds 1860s"
    )


async def test_autoscaler_uses_persisted_task_duration_settings_on_next_evaluate():
    store = InMemoryRunPodAutoscalerStateStore()
    await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile=None,
        task_duration_seconds_by_type={"img2img": 20},
        reason="test duration update",
        store=store,
        refresh_payload=False,
    )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=False,
        config=_config(),
        store=store,
        status_payload=_status(profile="img2img", pending=61, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["img2img"]
    assert payload["config"]["task_duration_seconds_by_type"]["img2img"] == 20
    assert decision["action"] == "scale_up"
    assert decision["estimated_pending_work_seconds"] == 1220
    assert decision["estimated_clear_time_seconds"] == 1220
    assert (
        decision["reason"]
        == "scale_up: estimated non-low-trust clear time 1220s exceeds 1200s"
    )


async def test_autoscaler_holds_paused_profile_without_scaling():
    calls = []
    store = InMemoryRunPodAutoscalerStateStore()
    await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile=None,
        task_duration_seconds_by_type=None,
        profile_autoscaler_paused_by_profile={"img2img": True},
        reason="pause img2img autoscaler",
        store=store,
        refresh_payload=False,
    )

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("paused profile should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=store,
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["img2img"]
    assert payload["config"]["profile_autoscaler_paused_by_profile"]["img2img"] is True
    assert "img2img" in payload["config"]["paused_profiles"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: profile autoscaler paused"
    assert decision["profile_autoscaler_paused"] is True
    assert calls == []


async def test_paused_profile_still_releases_idle_disabled_runpods():
    calls = []
    store = InMemoryRunPodAutoscalerStateStore()
    await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile=None,
        task_duration_seconds_by_type=None,
        profile_autoscaler_paused_by_profile={"wan22_video_v2": True},
        reason="pause wan22 autoscaler",
        store=store,
        refresh_payload=False,
    )

    async def start_delete(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-delete-paused",
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
        store=store,
        status_payload=_status(profile="wan22_video_v2", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("wan22_video_v2", "01", control_state="disabled"),
            _runpod_worker("wan22_video_v2", "02", control_state="disabled"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "wan22_video_v2"
    ]
    assert decision["action"] == "scale_down"
    assert decision["slot"] == "02"
    assert decision["profile_autoscaler_paused"] is True
    assert calls[0]["slot"] == "02"


async def test_autoscaler_profile_pause_does_not_pause_other_profiles():
    calls = []
    store = InMemoryRunPodAutoscalerStateStore()
    await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile=None,
        task_duration_seconds_by_type=None,
        profile_autoscaler_paused_by_profile={"scail2": True},
        reason="pause scail2 autoscaler",
        store=store,
        refresh_payload=False,
    )

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
        store=store,
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decisions = {item["profile"]: item for item in payload["decisions"]}
    assert decisions["img2img"]["action"] == "scale_up"
    assert decisions["scail2"]["action"] == "hold"
    assert decisions["scail2"]["reason"] == "hold: profile autoscaler paused"
    assert calls[0]["profile"] == "img2img"


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


@pytest.mark.parametrize(
    "updates",
    [
        {"unsupported": 30},
        {"img2img": 0},
        {"img2img": 3601},
    ],
)
async def test_autoscaler_rejects_invalid_task_duration_settings(updates):
    with pytest.raises(HTTPException) as exc_info:
        await set_runpod_autoscaler_settings_payload(
            scale_up_wait_minutes_by_profile=None,
            task_duration_seconds_by_type=updates,
            store=InMemoryRunPodAutoscalerStateStore(),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    "updates",
    [
        {"unknown": True},
        {"img2img": "maybe"},
    ],
)
async def test_autoscaler_rejects_invalid_profile_pause_settings(updates):
    with pytest.raises(HTTPException) as exc_info:
        await set_runpod_autoscaler_settings_payload(
            scale_up_wait_minutes_by_profile=None,
            task_duration_seconds_by_type=None,
            profile_autoscaler_paused_by_profile=updates,
            store=InMemoryRunPodAutoscalerStateStore(),
        )

    assert exc_info.value.status_code == 422


async def test_autoscaler_scales_up_when_backlog_has_no_accepting_workers():
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
        status_payload=_status(profile="image_to_video", pending=1, wait=10),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "image_to_video"
    ]
    assert decision["action"] == "scale_up"
    assert decision["capacity_status"] == "no_accepting_workers"
    assert decision["reason"] == "scale_up: no accepting workers for backlog"
    assert calls[0]["profile"] == "image_to_video"


async def test_autoscaler_holds_low_trust_only_backlog_without_accepting_workers():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(
            profile="image_to_video",
            pending=5,
            wait=10,
            non_low_trust_clear_pending_count_by_task_type={},
        ),
        workers_payload=_workers(),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "image_to_video"
    ]
    assert decision["action"] == "hold"
    assert decision["capacity_status"] == "no_non_low_trust_backlog"
    assert decision["reason"] == "hold: no non-low-trust backlog"
    assert calls == []


async def test_autoscaler_restarts_runpod_after_persistent_fault():
    calls = []

    async def start_restart(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-restart",
            action="restart",
            profile=kwargs["profile"],
            command=["runpod", "restart"],
            agent_id=kwargs["agent_id"],
            slot=kwargs["slot"],
            source="autoscaler",
            trigger_reason=kwargs["trigger_reason"],
        )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="scail2", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker(
                "scail2",
                "01",
                status="error",
                last_error_at=650.0,
            )
        ),
        operations_payload={"operations": []},
        start_restart_func=start_restart,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["scail2"]
    assert decision["action"] == "restart"
    assert decision["reason"] == "restart: runpod fault persisted 350s"
    assert decision["agent_id"] == "runpod_prod_scail2_manual_01"
    assert decision["slot"] == "01"
    assert calls == [
        {
            "profile": "scail2",
            "slot": "01",
            "agent_id": "runpod_prod_scail2_manual_01",
            "trigger_reason": "restart: runpod fault persisted 350s",
            "spawn_task_func": None,
        }
    ]
    assert payload["executed_operations"][0]["action"] == "restart"


async def test_autoscaler_waits_before_restarting_recent_runpod_fault():
    calls = []

    async def start_restart(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not restart before fault grace expires")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="scail2", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker(
                "scail2",
                "01",
                status="error",
                last_error_at=800.0,
            )
        ),
        operations_payload={"operations": []},
        start_restart_func=start_restart,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["scail2"]
    assert decision["action"] == "hold"
    assert calls == []


async def test_autoscaler_enables_paused_runpod_worker():
    calls = []

    async def start_enable(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-enable",
            action="enable",
            profile=kwargs["profile"],
            command=["runpod", "enable"],
            agent_id=kwargs["agent_id"],
            slot=kwargs["slot"],
            source="autoscaler",
            trigger_reason=kwargs["trigger_reason"],
        )

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="image_to_video", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker(
                "image_to_video",
                "03",
                status="idle",
                control_state="disabled",
            )
        ),
        operations_payload={"operations": []},
        start_enable_func=start_enable,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "image_to_video"
    ]
    assert decision["action"] == "enable"
    assert decision["reason"] == "enable: runpod paused worker available"
    assert decision["agent_id"] == "runpod_prod_image_to_video_manual_03"
    assert decision["slot"] == "03"
    assert calls == [
        {
            "profile": "image_to_video",
            "slot": "03",
            "agent_id": "runpod_prod_image_to_video_manual_03",
            "trigger_reason": "enable: runpod paused worker available",
            "spawn_task_func": None,
        }
    ]
    assert payload["executed_operations"][0]["action"] == "enable"


async def test_autoscaler_does_not_enable_residual_worker_after_successful_delete():
    calls = []

    async def start_enable(**kwargs):
        calls.append(kwargs)
        raise AssertionError("deleted worker must not be enabled from residual heartbeat")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="i2i_pro", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker(
                "i2i_pro",
                "02",
                status="idle",
                control_state="disabled",
            )
        ),
        operations_payload={
            "operations": [
                {
                    "id": "op-delete-i2i-pro-02",
                    "action": "delete",
                    "profile": "i2i_pro",
                    "slot": "02",
                    "agent_id": "runpod_prod_i2i_pro_manual_02",
                    "status": "succeeded",
                    "source": "autoscaler",
                    "ended_at": "1970-01-01T00:16:30Z",
                }
            ]
        },
        start_enable_func=start_enable,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: deleted runpod worker heartbeat awaiting expiry"
    assert decision["agent_id"] == "runpod_prod_i2i_pro_manual_02"
    assert decision["slot"] == "02"
    assert decision["deleted_worker_tombstone_remaining_seconds"] == 290
    assert calls == []
    assert payload["executed_operations"] == []


async def test_deleted_worker_tombstone_does_not_block_other_paused_runpod():
    calls = []

    async def start_enable(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-enable-i2i-pro-01",
            action="enable",
            profile=kwargs["profile"],
            command=["runpod", "enable"],
            agent_id=kwargs["agent_id"],
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
            _runpod_worker("i2i_pro", "01", control_state="disabled"),
            _runpod_worker("i2i_pro", "02", control_state="disabled"),
        ),
        operations_payload={
            "operations": [
                {
                    "id": "op-delete-i2i-pro-02",
                    "action": "delete",
                    "profile": "i2i_pro",
                    "slot": "02",
                    "agent_id": "runpod_prod_i2i_pro_manual_02",
                    "status": "succeeded",
                    "source": "manual",
                    "ended_at": "1970-01-01T00:16:30Z",
                }
            ]
        },
        start_enable_func=start_enable,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "enable"
    assert decision["agent_id"] == "runpod_prod_i2i_pro_manual_01"
    assert decision["slot"] == "01"
    assert calls[0]["agent_id"] == "runpod_prod_i2i_pro_manual_01"


async def test_autoscaler_executes_at_most_one_scale_up_per_round():
    calls = []
    status_payload = _status(profile="img2img", pending=100, wait=10)
    for detail in status_payload["runpod_profile_queue_details"]:
        if detail["profile"] == "scail2":
            detail["pending_count"] = 10
            detail["pending_count_by_task_type"] = {"scail2_action_transfer": 10}
            detail["non_low_trust_clear_pending_count"] = 10
            detail["non_low_trust_clear_pending_count_by_task_type"] = {
                "scail2_action_transfer": 10
            }
            detail["max_pending_wait_seconds"] = 10
            detail["pending_wait_records"] = [{"wait_seconds": 10, "priority": 1}]

    async def start_add(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id=f"op-add-{kwargs['profile']}",
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
        status_payload=status_payload,
        workers_payload=_workers(
            _local_worker("img2img,img2img_lora"),
            _local_worker("scail2_action_transfer"),
        ),
        operations_payload={"operations": []},
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decisions = {item["profile"]: item for item in payload["decisions"]}
    assert decisions["img2img"]["action"] == "scale_up"
    assert decisions["scail2"]["action"] == "scale_up"
    assert decisions["scail2"]["operation_skipped_reason"] == (
        "scale-up already executed this round"
    )
    assert [item["profile"] for item in calls] == ["img2img"]
    assert [item["profile"] for item in payload["executed_operations"]] == ["img2img"]


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


async def test_autoscaler_explains_active_runpod_bootstrap_wait():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not start add while bootstrap is active")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(),
        operations_payload={
            "operations": [
                _active_operation(
                    "img2img",
                    started_at="1970-01-01T00:10:00Z",
                    cleanup_slots=["03"],
                )
            ]
        },
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["img2img"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: runpod add still bootstrapping 400s"
    assert decision["runpod_bootstrap_elapsed_seconds"] == 400
    assert calls == []


async def test_autoscaler_retries_immediately_after_bootstrap_cleanup():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-retry",
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
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={
            "operations": [
                _failed_bootstrap_operation(
                    "img2img",
                    ended_at="1970-01-01T00:15:00Z",
                    slot="03",
                )
            ]
        },
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["img2img"]
    assert decision["action"] == "scale_up"
    assert decision["reason"].startswith("replace: previous runpod bootstrap timed out")
    assert decision["runpod_bootstrap_replacement_count"] == 1
    assert calls[0]["profile"] == "img2img"


async def test_autoscaler_holds_after_bootstrap_replacement_limit():
    calls = []

    async def start_add(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not retry after replacement limit")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="img2img", pending=100, wait=10),
        workers_payload=_workers(_local_worker("img2img,img2img_lora")),
        operations_payload={
            "operations": [
                _failed_bootstrap_operation(
                    "img2img",
                    ended_at="1970-01-01T00:15:00Z",
                    slot="03",
                    operation_id="failed-1",
                ),
                _failed_bootstrap_operation(
                    "img2img",
                    ended_at="1970-01-01T00:14:00Z",
                    slot="04",
                    operation_id="failed-2",
                ),
            ]
        },
        start_add_func=start_add,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["img2img"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: bootstrap replacement limit reached"
    assert decision["runpod_bootstrap_replacement_count"] == 2
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
    assert decision["reason"] == "hold: max runpod capacity reached"
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
            _local_worker("i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap"),
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
            "trigger_reason": "scale_down: no backlog and idle runpod available",
            "spawn_task_func": None,
        }
    ]


async def test_autoscaler_scales_down_idle_pornmaster_flux2_edit_bf16_runpod():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        return RunPodAdminOperation(
            id="op-delete-bf16",
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
        status_payload=_status(
            profile="pornmaster_flux2_edit_bf16",
            pending=0,
            wait=None,
        ),
        workers_payload=_workers(
            _runpod_worker("pornmaster_flux2_edit_bf16", "02"),
            _local_worker("pornmaster_flux2_edit_bf16"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}[
        "pornmaster_flux2_edit_bf16"
    ]
    assert decision["action"] == "scale_down"
    assert calls == [
        {
            "profile": "pornmaster_flux2_edit_bf16",
            "slot": "02",
            "trigger_reason": "scale_down: no backlog and idle runpod available",
            "spawn_task_func": None,
        }
    ]


async def test_autoscaler_skips_locked_runpod_scale_down_candidate():
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
            _runpod_worker("i2i_pro", "02", runpod_locked=True),
            _local_worker("i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "scale_down"
    assert decision["slot"] == "01"
    assert decision["runpod_locked_count"] == 1
    assert decision["runpod_locked_idle_count"] == 1
    assert calls[0]["slot"] == "01"


async def test_autoscaler_holds_when_all_idle_runpod_candidates_are_locked():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not delete locked runpod")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="i2i_pro", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("i2i_pro", "01", runpod_locked=True),
            _local_worker("i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap"),
        ),
        operations_payload={"operations": []},
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "hold"
    assert decision["reason"] == "hold: all idle runpod candidates are locked"
    assert decision["runpod_locked_count"] == 1
    assert calls == []


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
    assert decision["reason"] == "hold: minimum total accepting capacity reached"
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
    assert decision["reason"] == "hold: no idle runpod candidate"
    assert calls == []


async def test_autoscaler_holds_scale_down_for_autoscaler_minimum_lifetime():
    calls = []

    async def start_delete(**kwargs):
        calls.append(kwargs)
        raise AssertionError("should not delete")

    payload = await evaluate_runpod_autoscaler_once(
        mutate=True,
        config=_config(min_runpod_lifetime_seconds=1800),
        store=InMemoryRunPodAutoscalerStateStore(),
        status_payload=_status(profile="i2i_pro", pending=0, wait=None),
        workers_payload=_workers(
            _runpod_worker("i2i_pro", "01"),
            _local_worker("i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap"),
        ),
        operations_payload={
            "operations": [
                _finished_autoscaler_operation(
                    "i2i_pro",
                    ended_at="1970-01-01T00:05:00Z",
                    cleanup_slots=["01"],
                )
            ]
        },
        start_delete_func=start_delete,
        now_func=lambda: 1000.0,
    )

    decision = {item["profile"]: item for item in payload["decisions"]}["i2i_pro"]
    assert decision["action"] == "hold"
    assert decision["slot"] == "01"
    assert decision["minimum_lifetime_remaining_seconds"] == 1100
    assert decision["reason"] == "hold: minimum lifetime remaining 1100s"
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
