import pytest

from ops.gpu_pool_controller.providers.runpod import RunPodSettings
from ops.gpu_pool_controller.runpod_pod_request import RunPodPodRequestBuilder
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_AUTOSCALER_PROFILE_OPTIONS,
    RUNPOD_MINIMAX_H3_COMFY_EXTRA_ARGS,
    RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY,
    RUNPOD_MINIMAX_H3_MODEL_PREFIX,
    RUNPOD_MINIMAX_H3_SUPPORTED_TASK_TYPES,
    RUNPOD_TASK_PROFILES,
)


def test_minimax_h3_runpod_request_is_exact_autoscaled_profile():
    digest = "ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:" + "a" * 64
    builder = RunPodPodRequestBuilder(
        RunPodSettings(
            image_name_minimax_h3=digest,
            prod_agent_id="runpod_prod_minimax_h3_manual_01",
            min_download_mbps_minimax_h3=2000,
            min_ram_per_gpu_minimax_h3=128,
        )
    )
    body = builder.create_pod_body(
        task_type="minimax_h3_flf2v", environment="cloud-test"
    )
    prod_body = builder.create_pod_body(
        task_type="minimax_h3_ref2v", environment="cloud-prod"
    )

    assert body["imageName"] == digest
    assert body["gpuTypeIds"] == ["NVIDIA GeForce RTX 5090"]
    assert body["containerDiskInGb"] >= 100
    assert body["volumeInGb"] >= 100
    assert body["minDownloadMbps"] == 2000
    assert body["minRAMPerGPU"] == 128
    assert body["env"]["POOL_RUNTIME_PROFILE"] == "minimax_h3"
    assert body["env"]["COMFYUI_DIR"] == "/opt/ComfyUI"
    assert body["env"]["RUNPOD_MODEL_TARGET_DIR"] == "/workspace/ComfyUI/models"
    assert body["env"]["MINIMAX_H3_FORCE_PYTORCH_ATTENTION"] == "true"
    assert body["env"]["COMFY_EXTRA_ARGS"] == RUNPOD_MINIMAX_H3_COMFY_EXTRA_ARGS
    assert prod_body["env"]["RUNPOD_MODEL_SYNC_ENABLED"] == "true"
    assert prod_body["env"]["RUNPOD_MODEL_DOWNLOAD_CONCURRENCY"] == "4"
    assert prod_body["env"]["RUNPOD_START_SSHD"] == "true"
    assert prod_body["env"]["RUNPOD_INSTALL_SSHD_IF_MISSING"] == "true"
    assert prod_body["env"]["RUNPOD_MODEL_PREFIX"] == RUNPOD_MINIMAX_H3_MODEL_PREFIX
    assert body["env"]["SUPPORTED_TASK_TYPES"] == ",".join(
        RUNPOD_MINIMAX_H3_SUPPORTED_TASK_TYPES
    )
    assert body["env"]["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY


def test_minimax_h3_autoscaler_profile_pulls_all_public_execution_types():
    profile = next(
        option
        for option in RUNPOD_AUTOSCALER_PROFILE_OPTIONS
        if option["profile"] == "minimax_h3"
    )

    assert profile["supported_task_types"] == [
        "minimax_h3_t2v",
        "minimax_h3_i2v",
        "minimax_h3_flf2v",
        "minimax_h3_ref2v",
    ]


def test_minimax_h3_rejects_mutable_or_missing_image_reference():
    for image_name in ("", "ghcr.io/giraffu/allbot-gpu-minimax-h3:latest"):
        with pytest.raises(ValueError, match="pinned by sha256 digest"):
            RunPodPodRequestBuilder(
                RunPodSettings(image_name_minimax_h3=image_name)
            ).create_pod_body(task_type="minimax_h3_t2v", environment="cloud-test")


def test_minimax_h3_projected_cost_env_drives_scale_guard(monkeypatch):
    monkeypatch.setenv("RUNPOD_PROJECTED_COST_PER_HR_MINIMAX_H3", "0.99")

    settings = RunPodSettings.from_env()
    builder = RunPodPodRequestBuilder(settings)

    assert settings.projected_cost_per_hr_minimax_h3 == pytest.approx(0.99)
    assert builder.configured_projected_cost(
        RUNPOD_TASK_PROFILES["minimax_h3"]
    ) == pytest.approx(0.99)


def test_minimax_h3_resource_gate_env_is_rendered(monkeypatch):
    monkeypatch.setenv("RUNPOD_MIN_DOWNLOAD_MBPS_MINIMAX_H3", "2000")
    monkeypatch.setenv("RUNPOD_MIN_RAM_PER_GPU_MINIMAX_H3", "128")

    settings = RunPodSettings.from_env()

    assert settings.min_download_mbps_minimax_h3 == 2000
    assert settings.min_ram_per_gpu_minimax_h3 == 128


def test_minimax_h3_allows_pro_6000_server_with_resource_gates():
    digest = "ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:" + "b" * 64
    body = RunPodPodRequestBuilder(
        RunPodSettings(
            image_name_minimax_h3=digest,
            gpu_type_ids_minimax_h3=(
                "NVIDIA RTX PRO 6000 Blackwell Server Edition",
            ),
            min_download_mbps_minimax_h3=2000,
            min_ram_per_gpu_minimax_h3=128,
        )
    ).create_pod_body(task_type="minimax_h3_t2v", environment="cloud-test")

    assert body["gpuTypeIds"] == [
        "NVIDIA RTX PRO 6000 Blackwell Server Edition"
    ]
    assert body["minDownloadMbps"] == 2000
    assert body["minRAMPerGPU"] == 128


def test_minimax_h3_rejects_unverified_gpu_type():
    digest = "ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:" + "c" * 64

    with pytest.raises(ValueError, match="verified GPU types"):
        RunPodPodRequestBuilder(
            RunPodSettings(
                image_name_minimax_h3=digest,
                gpu_type_ids_minimax_h3=("NVIDIA L40S",),
            )
        ).create_pod_body(task_type="minimax_h3_t2v", environment="cloud-test")
