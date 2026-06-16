import pytest
from fastapi import HTTPException

from dashboard.backend.schemas import (
    RunPodScaleItem,
    RunPodScaleRequest,
    RunPodWorkerActionRequest,
)
from dashboard.backend.services import runpod_admin_service


@pytest.fixture(autouse=True)
def _clear_runpod_admin_operations():
    runpod_admin_service._operations.clear()
    yield
    runpod_admin_service._operations.clear()


def _discard_operation_coroutine(coro):
    coro.close()
    return None


@pytest.mark.asyncio
async def test_runpod_profiles_payload_lists_supported_prod_profiles():
    payload = await runpod_admin_service.get_runpod_profiles_payload()

    assert [item["profile"] for item in payload["profiles"]] == [
        "img2img",
        "image_to_video",
        "wan22_video_v2",
        "i2i_pro",
    ]
    assert payload["profiles"][0]["supported_task_types"] == [
        "img2img",
        "img2img_lora",
    ]


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_creates_retrying_operations():
    payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img_lora", count=2),
                RunPodScaleItem(profile="wan22_video_v2", count=1),
            ],
            max_attempts=100,
            retry_interval_seconds=30,
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    assert payload["status"] == "accepted"
    assert [operation["profile"] for operation in payload["operations"]] == [
        "img2img",
        "wan22_video_v2",
    ]
    command = payload["operations"][0]["command"]
    assert "add" in command
    assert command[command.index("--profile") + 1] == "img2img"
    assert command[command.index("--count") + 1] == "2"
    assert "--desired" not in command
    assert "--retry-unavailable" in command
    assert command[command.index("--max-attempts") + 1] == "100"
    assert command[command.index("--retry-interval") + 1] == "30"
    assert "--execute" in command
    assert payload["operations"][0]["action"] == "add"
    assert payload["operations"][0]["requested_count"] == 2
    assert "desired_count" not in payload["operations"][0]


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_treats_legacy_desired_as_add_count():
    payload = await runpod_admin_service.start_runpod_scale_payload(
        RunPodScaleRequest(
            items=[
                RunPodScaleItem(profile="img2img_lora", desired_count=1),
            ],
        ),
        spawn_task_func=_discard_operation_coroutine,
    )

    command = payload["operations"][0]["command"]
    assert "add" in command
    assert "--desired" not in command
    assert command[command.index("--count") + 1] == "1"
    assert payload["operations"][0]["requested_count"] == 1


@pytest.mark.asyncio
async def test_start_runpod_scale_payload_rejects_duplicate_profiles():
    with pytest.raises(HTTPException) as exc_info:
        await runpod_admin_service.start_runpod_scale_payload(
            RunPodScaleRequest(
                items=[
                    RunPodScaleItem(profile="img2img", desired_count=1),
                    RunPodScaleItem(profile="img2img_lora", desired_count=2),
                ],
            ),
            spawn_task_func=_discard_operation_coroutine,
        )

    assert exc_info.value.status_code == 422
    assert "duplicate profile" in exc_info.value.detail


@pytest.mark.asyncio
async def test_pause_and_delete_runpod_worker_build_slot_scoped_operations():
    action_request = RunPodWorkerActionRequest(prod_max_manual_slots=4)

    pause_payload = await runpod_admin_service.pause_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=action_request,
        spawn_task_func=_discard_operation_coroutine,
    )
    delete_payload = await runpod_admin_service.delete_runpod_worker_payload(
        agent_id="runpod_prod_wan22_video_v2_manual_03",
        request=action_request,
        spawn_task_func=_discard_operation_coroutine,
    )

    pause_command = pause_payload["operation"]["command"]
    delete_command = delete_payload["operation"]["command"]
    assert "disable" in pause_command
    assert "down" in delete_command
    assert pause_command[pause_command.index("--profile") + 1] == "wan22_video_v2"
    assert pause_command[pause_command.index("--slot") + 1] == "03"
    assert delete_command[delete_command.index("--slot") + 1] == "03"
    assert pause_payload["operation"]["status"] == "pending"
    assert delete_payload["operation"]["status"] == "pending"


def test_runpod_operation_env_opens_required_mutation_gates(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", raising=False)
    monkeypatch.delenv("RUNPOD_MAX_PODS_TOTAL", raising=False)
    monkeypatch.delenv("RUNPOD_MAX_PODS_PER_TYPE", raising=False)
    monkeypatch.delenv("RUNPOD_MAX_HOURLY_COST_USD", raising=False)
    env = runpod_admin_service._operation_env(prod_max_manual_slots=None)

    assert env["RUNPOD_DRY_RUN"] == "false"
    assert env["RUNPOD_AUTOSCALER_ENABLED"] == "true"
    assert "RUNPOD_MAX_PODS_TOTAL" not in env
    assert "RUNPOD_MAX_PODS_PER_TYPE" not in env
    assert "RUNPOD_MAX_HOURLY_COST_USD" not in env
    assert env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] == "100"


def test_runpod_env_defaults_prefer_container_env(monkeypatch, tmp_path):
    container_env = tmp_path / "container.env"
    cloud_test_env = tmp_path / ".env.cloud.test"
    cloud_prod_env = tmp_path / ".env.cloud.prod"
    container_env.write_text("APP_ENV=prod\n", encoding="utf-8")
    cloud_test_env.write_text("APP_ENV=test\n", encoding="utf-8")
    cloud_prod_env.write_text("APP_ENV=prod_file\n", encoding="utf-8")

    monkeypatch.delenv("DASHBOARD_RUNPOD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_RUNPOD_PROD_ENV_FILE", raising=False)
    monkeypatch.setenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", str(container_env))
    monkeypatch.setattr(runpod_admin_service, "PROJECT_ROOT", tmp_path)

    assert runpod_admin_service._runpod_env_file() == str(container_env)
    assert runpod_admin_service._prod_env_file() == str(container_env)
