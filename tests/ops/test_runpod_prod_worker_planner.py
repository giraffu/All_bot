import pytest

from ops.gpu_pool_controller.runpod_prod_worker_planner import (
    RunPodProdWorkerPlanError,
    RunPodProdWorkerPlanner,
)
from ops.gpu_pool_controller.runpod_profile_catalog import prod_agent_id_from_slot


def _pod(slot: str, *, profile: str = "img2img") -> dict:
    agent_id = prod_agent_id_from_slot(slot, max_manual_slots=8, profile=profile)
    return {
        "id": f"pod-{slot}",
        "name": f"pod-{slot}",
        "desiredStatus": "RUNNING",
        "env": {
            "RUNPOD_ENVIRONMENT": "cloud-prod",
            "RUNPOD_TASK_TYPE": profile,
            "AGENT_ID": agent_id,
        },
    }


def _worker(slot: str, *, profile: str = "img2img") -> dict:
    return {
        "agent_id": prod_agent_id_from_slot(
            slot,
            max_manual_slots=8,
            profile=profile,
        ),
        "types": "img2img,img2img_lora",
        "status": "idle",
        "provider": "runpod",
        "node_id": "runpod-cloud-prod",
        "runtime_profile": profile,
        "image_ref": "ghcr.io/test/image:tag",
        "current_task_id": None,
        "current_task_type": None,
    }


def test_build_add_plan_picks_free_slots_without_touching_existing_slots():
    planner = RunPodProdWorkerPlanner(max_manual_slots=4, profile="img2img")
    slot_pods = {"01": _pod("01"), "03": _pod("03")}

    plan = planner.build_add_plan(
        count=2,
        slot_pods=slot_pods,
        workers=[_worker("01"), _worker("04")],
    )

    assert plan["requested_count"] == 2
    assert plan["existing_slots"] == ["01", "03"]
    assert plan["free_slots"] == ["02", "04"]
    assert plan["create_slots"] == ["02", "04"]
    assert plan["enable_slots"] == []
    assert plan["delete_slots"] == []
    assert plan["slots"]["01"]["pod"]["id"] == "pod-01"
    assert plan["slots"]["04"]["worker"]["agent_id"] == "runpod_prod_img2img_manual_04"


def test_build_add_plan_rejects_when_not_enough_manual_slots_are_free():
    planner = RunPodProdWorkerPlanner(max_manual_slots=2, profile="img2img")

    with pytest.raises(RunPodProdWorkerPlanError, match="requires 2 free slot"):
        planner.build_add_plan(
            count=2,
            slot_pods={"01": _pod("01")},
            workers=[],
        )


def test_build_scale_plan_splits_create_enable_and_delete_slots():
    planner = RunPodProdWorkerPlanner(max_manual_slots=4, profile="img2img")

    plan = planner.build_scale_plan(
        desired=2,
        slot_pods={"01": _pod("01"), "03": _pod("03")},
        workers=[_worker("01")],
        controls={"01": {"state": "disabled"}, "03": {"state": "enabled"}},
    )

    assert plan["desired_slots"] == ["01", "02"]
    assert plan["existing_slots"] == ["01", "03"]
    assert plan["create_slots"] == ["02"]
    assert plan["enable_slots"] == ["01"]
    assert plan["delete_slots"] == ["03"]
    assert plan["slots"]["01"]["control"] == {"state": "disabled"}
    assert plan["slots"]["03"]["control"] == {"state": "enabled"}


def test_control_snapshot_slots_are_sorted_union_of_desired_and_existing():
    planner = RunPodProdWorkerPlanner(max_manual_slots=8, profile="img2img")

    assert planner.control_snapshot_slots(
        desired=2,
        slot_pods={"05": _pod("05"), "01": _pod("01")},
    ) == ["01", "02", "05"]


def test_would_execute_messages_match_existing_dry_run_contract():
    planner = RunPodProdWorkerPlanner(max_manual_slots=8, profile="wan22_video_v2")
    plan = {
        "create_slots": ["02"],
        "enable_slots": ["01"],
        "delete_slots": ["03"],
    }

    assert planner.scale_would_execute(plan) == [
        "set Central control for runpod_prod_wan22_video_v2_manual_02 to disabled",
        "create cloud-prod RunPod pod for slot 02",
        "wait for slot 02 Pod readiness and disabled heartbeat",
        "set Central control for runpod_prod_wan22_video_v2_manual_02 to enabled",
        "verify slot 01 heartbeat and set runpod_prod_wan22_video_v2_manual_01 to enabled",
        "set Central control for runpod_prod_wan22_video_v2_manual_03 to disabled",
        "wait until slot 03 worker has no current_task_id",
        "delete cloud-prod RunPod pod for slot 03",
    ]
    assert planner.add_would_execute({"create_slots": ["02"]}) == [
        "set Central control for new runpod_prod_wan22_video_v2_manual_02 to disabled",
        "create cloud-prod RunPod pod for new slot 02",
        "wait for new slot 02 Pod readiness and disabled heartbeat",
        "set Central control for new runpod_prod_wan22_video_v2_manual_02 to enabled",
        "leave all existing RunPod slots unchanged; no existing enable/disable/delete",
    ]
