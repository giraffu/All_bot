import pytest

from ops.gpu_pool_controller.providers.runpod import RunPodSettings
from ops.gpu_pool_controller.runpod_pod_request import RunPodPodRequestBuilder
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_AUTOSCALER_PROFILE_OPTIONS,
    RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY,
    RUNPOD_MINIMAX_H3_MODEL_PREFIX,
    RUNPOD_MINIMAX_H3_SUPPORTED_TASK_TYPES,
)


def test_minimax_h3_runpod_request_is_exact_autoscaled_profile():
    digest = "ghcr.io/giraffu/allbot-gpu-minimax-h3@sha256:" + "a" * 64
    builder = RunPodPodRequestBuilder(
        RunPodSettings(
            image_name_minimax_h3=digest,
            prod_agent_id="runpod_prod_minimax_h3_manual_01",
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
    assert body["env"]["POOL_RUNTIME_PROFILE"] == "minimax_h3"
    assert body["env"]["COMFYUI_DIR"] == "/opt/ComfyUI"
    assert body["env"]["RUNPOD_MODEL_TARGET_DIR"] == "/workspace/ComfyUI/models"
    assert prod_body["env"]["RUNPOD_MODEL_SYNC_ENABLED"] == "true"
    assert prod_body["env"]["RUNPOD_MODEL_DOWNLOAD_CONCURRENCY"] == "4"
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
