import importlib.util
import json
from pathlib import Path

import pytest

from ops.gpu_pool_controller.runpod_profile_catalog import (
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_TASK_PROFILES,
)
from src.workflow_mapping_validation import resolve_workflow_filename


ROOT = Path(__file__).resolve().parents[2]
MAIN_RUNTIME_TYPES_PATH = ROOT / "workers/comfy_agent/agent_runtime_types.py"
REMOTE_RUNTIME_TYPES_PATH = ROOT / "remote_workers/comfy_agent/agent_runtime_types.py"
MAIN_WORKFLOW_DIR = ROOT / "workers/comfy_agent/workflows"
REMOTE_VALIDATION_PATH = ROOT / "remote_workers/src/workflow_mapping_validation.py"
REMOTE_WORKFLOW_DIR = ROOT / "remote_workers/comfy_agent/workflows"
I2I_PRO_BASELINE_MODELS = {
    "qwen_3_8b_fp8mixed.safetensors",
    "flux2-vae.safetensors",
    "DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors",
    "z_image/qwen_3_4b.safetensors",
    "z_image/ae.safetensors",
    "DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors",
}
EXPECTED_MAIN_ONLY_WORKFLOWS = {
    "DasiwaLTX23WorkflowsI2VFLF2V_omniforgeCLTX23V39.json",
}
EXPECTED_REMOTE_WORKFLOW_DRIFTS = {
    "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json",
}
PROFILE_WORKFLOW_OVERRIDES = {
    "i2i_pro": json.loads(RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES),
    "ltx_video": json.loads(RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES),
}


def _load_remote_validation_module():
    spec = importlib.util.spec_from_file_location(
        "remote_workflow_mapping_validation",
        REMOTE_VALIDATION_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _workflow_files(workflow_dir: Path) -> set[str]:
    return {path.name for path in workflow_dir.glob("*.json")}


def test_remote_task_execution_context_matches_main_worker_contract():
    assert REMOTE_RUNTIME_TYPES_PATH.read_text(
        encoding="utf-8"
    ) == MAIN_RUNTIME_TYPES_PATH.read_text(encoding="utf-8")


def test_remote_workflow_directory_only_has_documented_drift():
    main_files = _workflow_files(MAIN_WORKFLOW_DIR)
    remote_files = _workflow_files(REMOTE_WORKFLOW_DIR)

    assert main_files - remote_files == EXPECTED_MAIN_ONLY_WORKFLOWS
    assert remote_files - main_files == set()

    changed_files = {
        filename
        for filename in main_files & remote_files
        if (MAIN_WORKFLOW_DIR / filename).read_bytes()
        != (REMOTE_WORKFLOW_DIR / filename).read_bytes()
    }
    assert changed_files == EXPECTED_REMOTE_WORKFLOW_DRIFTS


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
    remote_workflow = json.loads(
        (REMOTE_WORKFLOW_DIR / filename).read_text(encoding="utf-8")
    )

    assert main_workflow["26:149"]["inputs"]["last_frame_fix"] is True
    assert remote_workflow["26:149"]["inputs"]["last_frame_fix"] is True


def test_runpod_profile_supported_task_types_have_main_and_remote_workflow_files():
    for profile in RUNPOD_TASK_PROFILES.values():
        overrides = PROFILE_WORKFLOW_OVERRIDES.get(profile.runtime_profile, {})
        for task_type in profile.supported_task_types:
            filename = overrides.get(task_type, resolve_workflow_filename(task_type))
            assert (MAIN_WORKFLOW_DIR / filename).exists(), (
                profile.runtime_profile,
                task_type,
                filename,
            )
            assert (REMOTE_WORKFLOW_DIR / filename).exists(), (
                profile.runtime_profile,
                task_type,
                filename,
            )


def test_remote_worker_resolves_i2i_pro_task_type_workflow_overrides(monkeypatch):
    validation = _load_remote_validation_module()
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
    mappings = validation.validate_workflow_directory(str(REMOTE_WORKFLOW_DIR))
    assert {"face_swap_v2", "t2i-pornmaster-turbo", "i2i_pro"}.issubset(mappings)


@pytest.mark.parametrize("task_type", ["video_insert", "video_edit"])
def test_remote_legacy_video_task_types_resolve_to_wan22_aio_workflow(task_type):
    validation = _load_remote_validation_module()

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
def test_remote_scail2_task_types_resolve_to_api_workflows(task_type, filename):
    validation = _load_remote_validation_module()

    assert validation.resolve_workflow_filename(task_type) == filename


@pytest.mark.parametrize(
    "filename",
    ["face_swap_v2.json", "txt2img_from_i2i_pro.json", "i2i_pro.json"],
)
def test_remote_i2i_pro_workflows_stay_within_baseline_models(filename):
    refs = _workflow_model_refs(REMOTE_WORKFLOW_DIR / filename)

    assert refs <= I2I_PRO_BASELINE_MODELS
