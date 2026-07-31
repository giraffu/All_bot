import json
from pathlib import Path
import shlex

import pytest
from fastapi import HTTPException

from dashboard.backend.schemas import RunPodScaleItem
from dashboard.backend.services.runpod_admin_commands import (
    RunPodAdminCommandBuilder,
    RUNPOD_RELEASE_PROFILE_IMAGE_ENVS,
)


@pytest.fixture(autouse=True)
def _release_profile_pins(monkeypatch):
    pins = {
        image_env: f"ghcr.io/giraffu/profile-{index}@sha256:" + str(index) * 64
        for index, image_env in enumerate(
            sorted(RUNPOD_RELEASE_PROFILE_IMAGE_ENVS),
            start=1,
        )
    }
    monkeypatch.setenv("RUNPOD_RELEASE_PROFILE_PINS_JSON", json.dumps(pins))


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


def test_plan_add_command_is_read_only_and_excludes_reserved_slots(
    monkeypatch, tmp_path
):
    container_env = tmp_path / "container.env"
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", str(container_env))

    command = builder.plan_add_command(
        profile="img2img",
        count=2,
        excluded_slots=["01", "03"],
    )

    assert command[:4] == [
        "python3",
        str(tmp_path / "scripts" / "gpu_pool_controller.py"),
        "runpod",
        "prod-worker",
    ]
    assert command[command.index("--count") + 1] == "2"
    assert [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--exclude-slot"
    ] == ["01", "03"]
    assert "--execute" not in command


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


def test_lan_aio_control_command_uses_prod_fleet_helper(monkeypatch, tmp_path):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_OPS_SCRIPT", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_PROD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_AIO_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_MODEL_ENV_FILE", raising=False)
    container_env = tmp_path / "container.env"
    monkeypatch.setenv("DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", str(container_env))

    command = builder.lan_aio_control_command(
        "disable-aio",
        "gpu-177-gpu0-image_to_video",
    )

    assert command[:3] == [
        "python3",
        str(tmp_path / "scripts" / "lan_aio_fleet_prod_ops.py"),
        "disable-aio",
    ]
    assert command[command.index("--slot") + 1] == "gpu-177-gpu0-image_to_video"
    assert command[command.index("--prod-env-file") + 1] == str(container_env)
    assert command[command.index("--aio-env-file") + 1] == str(container_env)
    assert command[command.index("--model-env-file") + 1] == str(container_env)
    assert "--include-disabled" in command
    assert "--execute" in command


def test_lan_aio_action_command_rejects_slot_management_actions(tmp_path):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)

    for action in ("warm-cache", "takeover", "recover", "preflight"):
        with pytest.raises(ValueError) as exc_info:
            builder.lan_aio_action_command(
                action,
                "gpu-002-gpu1-pornmaster_flux2_edit",
            )

        assert f"unsupported LAN AIO action: {action}" in str(exc_info.value)


def test_lan_aio_action_command_can_run_on_lan_runner_over_ssh(monkeypatch, tmp_path):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("DASHBOARD_LAN_AIO_EXECUTION_MODE", "ssh")
    monkeypatch.setenv("DASHBOARD_LAN_AIO_RUNNER_HOST", "hfy@100.99.254.53")
    monkeypatch.setenv(
        "DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT",
        "/home/hfy/APP/All_bot",
    )
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_PROD_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_AIO_ENV_FILE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_MODEL_ENV_FILE", raising=False)

    command = builder.lan_aio_restart_command("gpu-002-gpu1-pornmaster_flux2_edit")

    assert command[:10] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
    ]
    assert command[10] == "StrictHostKeyChecking=accept-new"
    assert command[11] == "hfy@100.99.254.53"
    remote_command = command[12]
    assert remote_command.startswith("bash -lc ")
    remote_script = shlex.split(shlex.split(remote_command)[2])
    assert remote_script[:4] == [
        "cd",
        "/home/hfy/APP/All_bot",
        "&&",
        "python3",
    ]
    assert remote_script[4:7] == [
        "/home/hfy/APP/All_bot/scripts/lan_aio_fleet_prod_ops.py",
        "restart-aio",
        "--slot",
    ]
    assert "gpu-002-gpu1-pornmaster_flux2_edit" in remote_script
    assert "/home/hfy/APP/All_bot/.env.cloud.prod" in remote_script
    assert "/home/hfy/APP/All_bot/.env.lan-aio-prod" in remote_script
    assert "/home/hfy/APP/All_bot/.env.lan.model-cache" in remote_script
    assert "--execute" in remote_script


def test_lan_aio_action_command_requires_runner_host_for_ssh_mode(
    monkeypatch,
    tmp_path,
):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("DASHBOARD_LAN_AIO_EXECUTION_MODE", "ssh")
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_HOST", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        builder.lan_aio_restart_command("gpu-002-gpu1-pornmaster_flux2_edit")

    assert exc_info.value.status_code == 503
    assert "LAN AIO runner host is not configured" in exc_info.value.detail


def test_prod_lan_aio_action_never_falls_back_to_local_execution(
    monkeypatch,
    tmp_path,
):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.delenv("DASHBOARD_LAN_AIO_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_HOST", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        builder.lan_aio_control_command(
            "disable-aio",
            "gpu-252-gpu0-i2i_pro",
        )

    assert exc_info.value.status_code == 503
    assert "LAN AIO runner host is not configured" in exc_info.value.detail


def test_prod_lan_aio_runner_defaults_to_dedicated_openssh_port(
    monkeypatch,
    tmp_path,
):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("ALLBOT_ENV", "prod")
    monkeypatch.setenv("DASHBOARD_LAN_AIO_RUNNER_HOST", "hfy@100.99.254.53")
    monkeypatch.delenv("DASHBOARD_LAN_AIO_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_SSH_COMMAND", raising=False)
    monkeypatch.delenv("DASHBOARD_LAN_AIO_RUNNER_SSH_PORT", raising=False)

    command = builder.lan_aio_control_command(
        "disable-aio",
        "gpu-252-gpu0-i2i_pro",
    )

    assert command[:3] == ["ssh", "-p", "2222"]


def test_lan_aio_runner_command_exports_configured_proxy_env(
    monkeypatch,
    tmp_path,
):
    builder = RunPodAdminCommandBuilder(project_root=tmp_path)
    monkeypatch.setenv("DASHBOARD_LAN_AIO_EXECUTION_MODE", "ssh")
    monkeypatch.setenv("DASHBOARD_LAN_AIO_RUNNER_HOST", "hfy@100.99.254.53")
    monkeypatch.setenv("DASHBOARD_LAN_AIO_RUNNER_PROJECT_ROOT", "/home/hfy/APP/All_bot")
    monkeypatch.setenv(
        "DASHBOARD_LAN_AIO_RUNNER_HTTP_PROXY",
        "http://127.0.0.1:7890",
    )
    monkeypatch.setenv(
        "DASHBOARD_LAN_AIO_RUNNER_HTTPS_PROXY",
        "http://127.0.0.1:7890",
    )
    monkeypatch.setenv(
        "DASHBOARD_LAN_AIO_RUNNER_ALL_PROXY",
        "http://127.0.0.1:7890",
    )
    monkeypatch.setenv(
        "DASHBOARD_LAN_AIO_RUNNER_NO_PROXY",
        "127.0.0.1,localhost,192.168.1.115,192.168.1.2",
    )

    command = builder.lan_aio_control_command(
        "enable-aio",
        "gpu-002-gpu1-pornmaster_flux2_edit",
    )

    remote_command = shlex.split(command[-1])[2]
    assert "export http_proxy=http://127.0.0.1:7890" in remote_command
    assert "export HTTP_PROXY=http://127.0.0.1:7890" in remote_command
    assert "export https_proxy=http://127.0.0.1:7890" in remote_command
    assert "export HTTPS_PROXY=http://127.0.0.1:7890" in remote_command
    assert "export all_proxy=http://127.0.0.1:7890" in remote_command
    assert "export ALL_PROXY=http://127.0.0.1:7890" in remote_command
    assert (
        "export no_proxy=127.0.0.1,localhost,192.168.1.115,192.168.1.2"
        in remote_command
    )
    assert (
        "export NO_PROXY=127.0.0.1,localhost,192.168.1.115,192.168.1.2"
        in remote_command
    )


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


def test_operation_env_pins_release_profile_images_over_stale_container_env(
    monkeypatch,
):
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())
    pins = {
        image_env: f"ghcr.io/giraffu/profile-{index}@sha256:" + str(index) * 64
        for index, image_env in enumerate(
            sorted(RUNPOD_RELEASE_PROFILE_IMAGE_ENVS),
            start=1,
        )
    }
    monkeypatch.setenv("RUNPOD_RELEASE_PROFILE_PINS_JSON", json.dumps(pins))
    for image_env in pins:
        monkeypatch.setenv(image_env, "ghcr.io/giraffu/legacy:old")

    env = builder.operation_env()

    assert {image_env: env[image_env] for image_env in pins} == pins


def test_operation_env_rejects_mutable_or_incomplete_release_profile_pins(
    monkeypatch,
):
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())
    monkeypatch.setenv(
        "RUNPOD_RELEASE_PROFILE_PINS_JSON",
        json.dumps(
            {
                "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO": (
                    "ghcr.io/giraffu/allbot-gpu-wan22-aio-video:latest"
                )
            }
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        builder.operation_env()

    assert exc_info.value.status_code == 503
    assert "release profile pins" in exc_info.value.detail


def test_lan_aio_slot_selection_rejects_unknown_agent():
    builder = RunPodAdminCommandBuilder(project_root=Path.cwd())

    with pytest.raises(HTTPException) as exc_info:
        builder.lan_aio_slot_selection_or_422("lan_aio_prod_unknown_01")

    assert exc_info.value.status_code == 422
    assert "unsupported LAN AIO worker" in exc_info.value.detail
