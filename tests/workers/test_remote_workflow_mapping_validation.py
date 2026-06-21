import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
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


def test_remote_worker_resolves_i2i_pro_task_type_workflow_overrides(monkeypatch):
    validation = _load_remote_validation_module()
    monkeypatch.setenv(
        validation.WORKFLOW_FILENAME_OVERRIDES_ENV,
        (
            '{"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json",'
            '"face_swap":"face_swap_v2.json"}'
        ),
    )

    assert validation.resolve_workflow_filename("face_swap") == "face_swap_v2.json"
    assert (
        validation.resolve_workflow_filename("t2i-pornmaster-turbo")
        == "txt2img_from_i2i_pro.json"
    )
    mappings = validation.validate_workflow_directory(str(REMOTE_WORKFLOW_DIR))
    assert {"face_swap", "t2i-pornmaster-turbo", "i2i_pro"}.issubset(mappings)


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
