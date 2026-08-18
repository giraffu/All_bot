import json
from pathlib import Path

import pytest

from src import workflow_mapping_validation as canonical_validation
from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_TASK_PROFILES,
)
from ops.gpu_pool_controller.runtime import LAN_AIO_ALL_WORKFLOW_OVERRIDES
from src.workflow_mapping_validation import (
    resolve_workflow_filename,
    validate_workflow_directory,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN_WORKFLOW_DIR = ROOT / "workers/comfy_agent/workflows"
RUNPOD_WORKFLOW_DIR = MAIN_WORKFLOW_DIR
BAKED_PROFILE_DOCKERFILES = tuple(
    ROOT / "workers/runpod_profiles" / profile / "Dockerfile"
    for profile in (
        "img2img_lora",
        "face_swap",
        "i2i_pro",
        "wan22_aio_video",
        "scail2",
        "ltx_video",
        "pornmaster_flux2_edit",
    )
)
I2I_PRO_BASELINE_MODELS = {
    "qwen_3_8b_fp8mixed.safetensors",
    "flux2-vae.safetensors",
    "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors",
    "z_image/qwen_3_4b.safetensors",
    "z_image/ae.safetensors",
    "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors",
}
PROFILE_WORKFLOW_OVERRIDES = {
    "face_swap": json.loads(RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES),
    "i2i_pro": json.loads(RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES),
    "ltx_video": json.loads(RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES),
}


def _load_runpod_validation_module():
    return canonical_validation


def _workflow_model_refs(path: Path) -> set[str]:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    refs: set[str] = set()
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else {}
        if not isinstance(inputs, dict):
            continue
        for key in ("unet_name", "clip_name", "vae_name", "lora_name"):
            value = inputs.get(key)
            if isinstance(value, str) and value:
                refs.add(value)
    return refs


def test_lan_all_profile_validates_every_execution_workflow(monkeypatch):
    task_types = {
        "img2img",
        "img2img_lora",
        "image_to_video",
        "wan22_video_v2",
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
        "ltx_video",
        "ltx_video_flf2v",
        "ltx_video_v2v_audio",
        "i2i_pro",
        "t2i-pornmaster-turbo",
        "face_swap_v2",
        "face_swap",
        "ltx_t2v",
        "ltx_t2v_ic",
    }
    monkeypatch.setenv(
        "WORKFLOW_FILENAME_OVERRIDES",
        LAN_AIO_ALL_WORKFLOW_OVERRIDES,
    )

    mappings = validate_workflow_directory(str(MAIN_WORKFLOW_DIR))

    assert task_types <= set(mappings)


def test_scail2_flex_profile_validates_only_six_execution_workflows(monkeypatch):
    task_types = {
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
        "img2img",
        "img2img_lora",
    }
    monkeypatch.setenv(
        "WORKFLOW_FILENAME_OVERRIDES",
        LAN_AIO_ALL_WORKFLOW_OVERRIDES,
    )

    mappings = validate_workflow_directory(str(MAIN_WORKFLOW_DIR))

    assert task_types <= set(mappings)


@pytest.mark.parametrize("dockerfile_path", BAKED_PROFILE_DOCKERFILES)
def test_profile_image_build_fails_when_runpod_worker_bundle_cannot_import(
    dockerfile_path,
):
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert (
        "COPY workers/comfy_agent /opt/allbot/runtime/runpod_worker/comfy_agent"
        in dockerfile
    )
    assert "COPY src /opt/allbot/runtime/runpod_worker/src" in dockerfile
    assert "PYTHONPATH=/opt/allbot/runtime/runpod_worker python3 -c" in dockerfile
    assert "from comfy_agent.workflow_task_patchers import TASK_SPECIFIC_PATCHERS" in dockerfile


@pytest.mark.parametrize(
    "filename",
    [
        "LTX 2.3 FLF2V 6.1.json",
        "LTX 2.3 10Eros v1.2 FLF2V 6.1.json",
    ],
)
def test_ltx_flf2v_workflows_enable_last_frame_decode_fix(filename):
    main_workflow = json.loads(
        (MAIN_WORKFLOW_DIR / filename).read_text(encoding="utf-8")
    )
    assert main_workflow["26:149"]["inputs"]["last_frame_fix"] is True


def test_runpod_profile_supported_task_types_have_main_and_runpod_workflow_files():
    for profile in RUNPOD_TASK_PROFILES.values():
        overrides = PROFILE_WORKFLOW_OVERRIDES.get(profile.runtime_profile, {})
        for task_type in profile.supported_task_types:
            filename = overrides.get(task_type, resolve_workflow_filename(task_type))
            assert (MAIN_WORKFLOW_DIR / filename).exists(), (
                profile.runtime_profile,
                task_type,
                filename,
            )
            assert (RUNPOD_WORKFLOW_DIR / filename).exists(), (
                profile.runtime_profile,
                task_type,
                filename,
            )


def test_runpod_worker_resolves_i2i_pro_task_type_workflow_overrides(monkeypatch):
    validation = _load_runpod_validation_module()
    monkeypatch.setenv(
        validation.WORKFLOW_FILENAME_OVERRIDES_ENV,
        (
            '{"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json",'
            '"face_swap_v2":"face_swap_v2.json"}'
        ),
    )

    assert validation.resolve_workflow_filename("face_swap_v2") == "face_swap_v2.json"
    assert (
        validation.resolve_workflow_filename("t2i-pornmaster-turbo")
        == "txt2img_from_i2i_pro.json"
    )
    mappings = validation.validate_workflow_directory(str(RUNPOD_WORKFLOW_DIR))
    assert {"face_swap_v2", "t2i-pornmaster-turbo", "i2i_pro"}.issubset(mappings)


@pytest.mark.parametrize(
    ("task_type", "filename"),
    [
        ("ltx_video_v2", "LTX 2.3 10Eros v1.4 DMD I2V.json"),
        ("ltx_video_v2_flf2v", "LTX 2.3 10Eros v1.4 DMD FLF2V.json"),
    ],
)
def test_runpod_worker_resolves_ltx_v2_workflow_filenames(task_type, filename):
    validation = _load_runpod_validation_module()

    assert validation.resolve_workflow_filename(task_type) == filename


def test_face_swap_profile_routes_v1_and_v2_to_v2_workflow(monkeypatch):
    validation = _load_runpod_validation_module()
    overrides = json.loads(RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES)

    assert overrides == {
        "face_swap": "face_swap_v2.json",
        "face_swap_v2": "face_swap_v2.json",
    }

    monkeypatch.setenv(
        validation.WORKFLOW_FILENAME_OVERRIDES_ENV,
        RUNPOD_FACE_SWAP_WORKFLOW_OVERRIDES,
    )

    assert validation.resolve_workflow_filename("face_swap") == "face_swap_v2.json"
    assert validation.resolve_workflow_filename("face_swap_v2") == "face_swap_v2.json"


@pytest.mark.parametrize("task_type", ["video_insert", "video_edit"])
def test_runpod_legacy_video_task_types_resolve_to_wan22_aio_workflow(task_type):
    validation = _load_runpod_validation_module()

    assert validation.resolve_workflow_filename(task_type) == "Wan22AioV82.json"


@pytest.mark.parametrize(
    ("task_type", "filename"),
    [
        ("ltx_video_flf2v", "LTX 2.3 FLF2V 6.1.json"),
        ("ltx_video_v2v_audio", "LTX 2.3 V2V Audio 6.1.json"),
        ("scail2_action_transfer", "SCAIL-2_Animation_multi-char_audio.api.json"),
        (
            "scail2_action_transfer_long",
            "SCAIL-2_Animation_WAN-Context-Windows.api.json",
        ),
        ("scail2_video_replacement", "SCAIL-2_Replacement_audio.api.json"),
        (
            "scail2_face_swap_v2",
            "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
        ),
    ],
)
def test_runpod_scail2_task_types_resolve_to_api_workflows(task_type, filename):
    validation = _load_runpod_validation_module()

    assert validation.resolve_workflow_filename(task_type) == filename


@pytest.mark.parametrize(
    "filename",
    ["face_swap_v2.json", "txt2img_from_i2i_pro.json", "i2i_pro.json"],
)
def test_runpod_i2i_pro_workflows_stay_within_baseline_models(filename):
    refs = _workflow_model_refs(RUNPOD_WORKFLOW_DIR / filename)

    assert refs <= I2I_PRO_BASELINE_MODELS
