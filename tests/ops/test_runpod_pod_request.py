from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    RUNPOD_I2I_PRO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX,
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX,
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
    RUNPOD_SCAIL2_DOCKER_START_CMD,
    RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    RUNPOD_SCAIL2_MODEL_PREFIX,
    RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodProvider,
    RunPodSettings,
    prod_agent_id_from_slot,
)
from ops.gpu_pool_controller.runpod_pod_request import RunPodPodRequestBuilder


I2I_PRO_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:"
    "20260614-i2ipro-b75c6a9-cu128-min5-ssh"
)
SCAIL2_IMAGE = RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX + "20260617-scail2-prod"
LTX_VIDEO_IMAGE = RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX + "20260622-ltx-prod"
PORNMASTER_FLUX2_EDIT_IMAGE = (
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX
    + "20260701-pornmaster-flux2-edit"
)


def _settings_for_profile(profile: str) -> RunPodSettings:
    return RunPodSettings(
        api_key="rp_test_key",
        minio_endpoint="https://r2.example.test",
        prod_agent_id=prod_agent_id_from_slot("01", profile=profile),
        model_bucket="allbot-model-cache",
        image_name_i2i_pro=I2I_PRO_IMAGE,
        image_name_scail2=SCAIL2_IMAGE,
        image_name_ltx_video=LTX_VIDEO_IMAGE,
        image_name_pornmaster_flux2_edit=PORNMASTER_FLUX2_EDIT_IMAGE,
        model_prefix_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
        model_manifest_key_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        model_prefix_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
        model_manifest_key_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
        model_prefix_i2i_pro=RUNPOD_I2I_PRO_MODEL_PREFIX,
        model_manifest_key_i2i_pro=RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
        model_prefix_scail2=RUNPOD_SCAIL2_MODEL_PREFIX,
        model_manifest_key_scail2=RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
        model_prefix_ltx_video=RUNPOD_LTX_VIDEO_MODEL_PREFIX,
        model_manifest_key_ltx_video=RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
        model_prefix_pornmaster_flux2_edit=RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
        model_manifest_key_pornmaster_flux2_edit=(
            RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
        ),
    )


def test_pod_request_builder_matches_provider_render_for_prod_profiles():
    cases = [
        ("img2img", "img2img"),
        ("image_to_video", "image_to_video"),
        ("wan22_video_v2", "wan22_video_v2"),
        ("i2i_pro", "i2i_pro"),
        ("scail2", "scail2"),
        ("ltx_video", "ltx_video"),
        ("pornmaster_flux2_edit", "pornmaster_flux2_edit"),
    ]
    for task_type, profile in cases:
        settings = _settings_for_profile(profile)
        builder_body = RunPodPodRequestBuilder(settings).create_pod_body(
            task_type=task_type,
            environment="cloud-prod",
        )
        provider_body = RunPodProvider(settings).render_create_pod_request(
            task_type=task_type,
            environment="cloud-prod",
            redact=False,
        )["json"]

        assert builder_body == provider_body


def test_pod_request_builder_keeps_profile_specific_prod_env():
    img2img = RunPodPodRequestBuilder(_settings_for_profile("img2img")).create_pod_body(
        task_type="img2img",
        environment="cloud-prod",
    )
    wan22 = RunPodPodRequestBuilder(
        _settings_for_profile("wan22_video_v2")
    ).create_pod_body(
        task_type="wan22_video_v2",
        environment="cloud-prod",
    )
    i2i = RunPodPodRequestBuilder(_settings_for_profile("i2i_pro")).create_pod_body(
        task_type="i2i_pro",
        environment="cloud-prod",
    )
    scail2 = RunPodPodRequestBuilder(_settings_for_profile("scail2")).create_pod_body(
        task_type="scail2",
        environment="cloud-prod",
    )
    ltx = RunPodPodRequestBuilder(_settings_for_profile("ltx_video")).create_pod_body(
        task_type="ltx_video",
        environment="cloud-prod",
    )
    pornmaster = RunPodPodRequestBuilder(
        _settings_for_profile("pornmaster_flux2_edit")
    ).create_pod_body(
        task_type="pornmaster_flux2_edit",
        environment="cloud-prod",
    )

    assert img2img["imageName"] == RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
    assert img2img["dockerStartCmd"] == list(RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD)
    assert wan22["imageName"] == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    assert wan22["env"]["COMFY_EXTRA_ARGS"] == RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS
    assert wan22["env"]["WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"] == "600"
    assert i2i["env"]["TASK_TYPE_WORKFLOW_OVERRIDES"] == RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    assert i2i["env"]["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    assert scail2["dockerStartCmd"] == list(RUNPOD_SCAIL2_DOCKER_START_CMD)
    assert scail2["env"]["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
    assert ltx["imageName"] == LTX_VIDEO_IMAGE
    assert ltx["containerDiskInGb"] == RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB
    assert ltx["env"]["TASK_TYPE_WORKFLOW_OVERRIDES"] == RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    assert ltx["env"]["RUNPOD_MODEL_MANIFEST_KEY"] == RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
    assert pornmaster["imageName"] == PORNMASTER_FLUX2_EDIT_IMAGE
    assert pornmaster["containerDiskInGb"] == RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB
    assert pornmaster["dockerStartCmd"] == list(
        RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD
    )
    assert pornmaster["env"]["SUPPORTED_TASK_TYPES"] == (
        "pornmaster_flux2_single_edit,pornmaster_flux2_multi_edit"
    )
    assert (
        pornmaster["env"]["RUNPOD_MODEL_PREFIX"]
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX
    )
    assert (
        pornmaster["env"]["RUNPOD_MODEL_MANIFEST_KEY"]
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
    )
