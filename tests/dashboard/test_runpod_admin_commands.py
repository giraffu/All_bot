from pathlib import Path

import pytest
from fastapi import HTTPException

from dashboard.backend.schemas import RunPodScaleItem
from dashboard.backend.services.runpod_admin_commands import (
    RunPodAdminCommandBuilder,
)


def test_base_command_uses_container_env_files_and_slot(monkeypatch, tmp_path):
    container_env = tmp_path / "container.env"
    container_env.write_text("APP_ENV=prod\n", encoding="utf-8")
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)

    monkeypatch.delenv("DASHBOARD_RUNPOD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_RUNPOD_PROD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_RUNPOD_OPS_SCRIPT", raising=False)
    monkeypatch.setenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", str(container_env))

    command = builder.base_command("restart", profile="wan22_video_v2", slot="03")

    assert command[:3] == [
        "bash",
        str(tmp_path / "scripts" / "runpod_prod_ops.sh"),
        "restart",
    ]
    assert command[command.index("--profile") + 1] == "wan22_video_v2"
    assert command[command.index("--slot") + 1] == "03"
    assert command[command.index("--runpod-env-file") + 1] == str(container_env)
    assert command[command.index("--prod-env-file") + 1] == str(container_env)


def test_requested_count_accepts_legacy_desired_count():
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())

    assert (
        builder.requested_count_or_422(
            RunPodScaleItem(profile="img2img", desired_count=3)
        )
        == 3
    )


def test_requested_count_rejects_missing_count():
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())

    with pytest.raises(HTTPException) as exc_info:
        builder.requested_count_or_422(RunPodScaleItem(profile="img2img"))

    assert exc_info.value.status_code == 422
    assert "count is required" in exc_info.value.detail


def test_profile_and_agent_selection_match_runpod_provider_aliases():
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())

    assert builder.normalize_profile_or_422("img2img_lora") == "img2img"
    assert builder.agent_selection_or_422(
        "runpod_prod_wan22_video_v2_manual_03",
        max_manual_slots=10,
    ) == ("wan22_video_v2", "03")


def test_lan_aio_restart_command_uses_prod_fleet_helper(monkeypatch, tmp_path):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_OPS_SCRIPT", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_PROD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_AIO_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_MODEL_ENV_FILE", raising=False)

    command = builder.lan_aio_restart_command("gpu-177-gpu0-image_to_video")

    assert command[:3] == [
        "python3",
        str(tmp_path / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "restart-aio",
    ]
    assert command[command.index("--slot") + 1] == "gpu-177-gpu0-image_to_video"
    assert "--execute" in command


def test_operation_env_opens_mutation_gates_and_drops_legacy_limits(monkeypatch):
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())
    monkeypatch.setenv("RUNPOD_DRY_RUN", "true")
    monkeypatch.setenv("RUNPOD_AUTOSCALER_ENABLED", "false")
    monkeypatch.setenv("RUNPOD_MAX_PODS_TOTAL", "1")
    monkeypatch.setenv("RUNPOD_MAX_PODS_PER_TYPE", "1")
    monkeypatch.setenv("RUNPOD_MAX_HOURLY_COST_USD", "1")

    env = builder.operation_env(prod_max_manual_slots=9)

    assert env["RUNPOD_DRY_RUN"] == "false"
    assert env["RUNPOD_AUTOSCALER_ENABLED"] == "true"
    assert env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] == "9"
    assert "RUNPOD_MAX_PODS_TOTAL" not in env
    assert "RUNPOD_MAX_PODS_PER_TYPE" not in env
    assert "RUNPOD_MAX_HOURLY_COST_USD" not in env


def test_lan_aio_slot_selection_rejects_unknown_agent():
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())

    with pytest.raises(HTTPException) as exc_info:
        builder.lan_aio_slot_selection_or_422("lan_aio_prod_unknown_01")

    assert exc_info.value.status_code == 422
    assert "unsupported LAN AIO worker" in exc_info.value.detail
