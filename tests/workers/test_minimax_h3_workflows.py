import json
from pathlib import Path

import pytest

from scripts.build_minimax_h3_api_workflows import build
from src.workflow_mapping_validation import resolve_workflow_filename, validate_workflow_directory
from workers.comfy_agent.workflow_patcher import WorkflowPatcher


TASKS = {
    "minimax_h3_t2v": "MiniMax H3 T2V.api.json",
    "minimax_h3_i2v": "MiniMax H3 I2V.api.json",
    "minimax_h3_flf2v": "MiniMax H3 FLF2V.api.json",
    "minimax_h3_ref2v": "MiniMax H3 REF2V.api.json",
}


def test_minimax_h3_api_workflows_are_deterministic_and_synced():
    validate_workflow_directory("workers/comfy_agent/workflows")
    for task_type, filename in TASKS.items():
        assert resolve_workflow_filename(task_type) == filename
        main = Path("workers/comfy_agent/workflows") / filename
        runpod = Path("workers/runpod_runtime/comfy_agent/workflows") / filename
        assert main.read_bytes() == runpod.read_bytes()
        workflow = json.loads(main.read_text())
        assert workflow == build(task_type)
        assert "nodes" not in workflow
        if task_type in {"minimax_h3_t2v", "minimax_h3_i2v"}:
            assert workflow["3"]["inputs"] == {
                "model": ["2", 0],
                "shift_video": 12.0,
                "shift_audio": 3.0,
            }
            assert workflow["10"]["inputs"] == {
                "model": ["1", 0],
                "lora_name": "MiniMaxH3/HMBreasts_085e0750_e40.safetensors",
                "strength_model": 1.0,
            }
            assert workflow["11"]["inputs"] == {
                "model": ["10", 0],
                "lora_name": "MiniMaxH3/vagassist_e40.safetensors",
                "strength_model": 1.0,
            }
            assert workflow["12"]["inputs"] == {
                "model": ["11", 0],
                "lora_name": "MiniMaxH3/hmpussy_v6_epoch30.safetensors",
                "strength_model": 0.35,
            }
            assert workflow["13"]["inputs"] == {
                "model": ["12", 0],
                "lora_name": "MiniMaxH3/HMNSFW_AIO_V2.safetensors",
                "strength_model": 0.5,
            }
            assert workflow["14"]["inputs"] == {
                "model": ["13", 0],
                "lora_name": "MiniMaxH3/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy_resized_avg_rank_21_bf16.safetensors",
                "strength_model": 0.75,
            }
            assert workflow["2"]["inputs"]["model"] == ["14", 0]
            assert workflow["34"]["inputs"]["steps"] == 6
            assert workflow["33"] == {
                "inputs": {},
                "class_type": "MiniMaxH3TurboSampler",
            }
            assert workflow["35"]["inputs"]["sampler"] == ["33", 0]
        elif task_type == "minimax_h3_flf2v":
            assert workflow["10"]["inputs"]["lora_name"] == "MiniMaxH3/HMBreasts_085e0750_e40.safetensors"
            assert workflow["10"]["inputs"]["strength_model"] == 1.0
            assert workflow["11"]["inputs"]["lora_name"] == "MiniMaxH3/vagassist_e40.safetensors"
            assert workflow["11"]["inputs"]["strength_model"] == 1.0
            assert workflow["12"]["inputs"]["lora_name"] == "MiniMaxH3/hmpussy_v6_epoch30.safetensors"
            assert workflow["12"]["inputs"]["strength_model"] == 0.35
            assert "13" not in workflow and "14" not in workflow
            assert workflow["2"]["inputs"]["model"] == ["12", 0]
            assert workflow["34"]["inputs"]["steps"] == 25
            assert workflow["33"]["inputs"]["sampler_name"] == "res_multistep"
        else:
            assert workflow["3"]["inputs"] == {
                "model": ["2", 0],
                "shift_video": 11.0,
                "shift_audio": 4.0,
            }
            assert not {"10", "11", "12", "13", "14"} & workflow.keys()
            assert workflow["2"]["inputs"]["model"] == ["1", 0]
            assert workflow["34"]["inputs"]["steps"] == 25
            assert workflow["33"]["inputs"]["sampler_name"] == "res_multistep"
        assert workflow["38"]["inputs"]["audio"] == ["37", 0]
        assert workflow["40"]["class_type"] == "SaveImage"
        assert workflow["39"]["inputs"]["batch_index"] == 4095
        if task_type in {"minimax_h3_i2v", "minimax_h3_flf2v"}:
            assert workflow["41"]["class_type"] == "DaSiWa_ResolutionScaleCalculator"
            assert workflow["41"]["inputs"] == {
                "resolution_preset": "0.26 MP - Preview",
                "no_scale": False,
                "scale_from_image": True,
                "aspect_preset_when_not_image": "9:16 - Social",
                "swap_aspect_when_not_image": False,
                "custom_aspect_width": 16,
                "custom_aspect_height": 9,
                "mode": "WAN/LTX (Div32)",
                "custom_divisor": 8,
                "image": ["20", 0],
            }
            assert workflow["30"]["inputs"]["width"] == ["41", 0]
            assert workflow["30"]["inputs"]["height"] == ["41", 1]
        else:
            assert "41" not in workflow


def test_minimax_h3_patcher_orders_refs_and_removes_unused_slots():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")
    result = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {
            "prompt": "walk together",
            "image": "first.png",
            "image2": "second.png",
            "reference_descriptions": ["adult woman", "adult man"],
            "width": 416,
            "height": 736,
            "frame_count": 124,
            "seed": 9,
        },
    )
    assert result["20"]["inputs"]["image"] == "first.png"
    assert result["21"]["inputs"]["image"] == "second.png"
    assert "22" not in result and "23" not in result
    assert result["30"]["inputs"]["ref_images.ref_image_0"] == ["20", 0]
    assert result["30"]["inputs"]["ref_images.ref_image_1"] == ["21", 0]
    assert "ref_images.ref_image_2" not in result["30"]["inputs"]
    assert "ref_images.ref_image_3" not in result["30"]["inputs"]
    assert not {
        f"ref_image_{index}" for index in range(1, 5)
    } & result["30"]["inputs"].keys()
    assert result["30"]["inputs"]["prompt"].startswith("<Picture 1>: adult woman\n<Picture 2>: adult man")


def test_minimax_h3_output_prefix_is_unique_per_execution():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")

    first = patcher.patch_workflow(
        "minimax_h3_t2v",
        workflow,
        {"prompt": "scene", "seed": 7},
        execution_id="task/one",
    )
    second = patcher.patch_workflow(
        "minimax_h3_t2v",
        workflow,
        {"prompt": "scene", "seed": 7},
        execution_id="task/two",
    )

    assert first["38"]["inputs"]["filename_prefix"] == "minimax_h3_t2v_task_one"
    assert first["40"]["inputs"]["filename_prefix"] == "minimax_h3_t2v_task_one_last_frame"
    assert second["38"]["inputs"]["filename_prefix"] == "minimax_h3_t2v_task_two"
    assert first["38"]["inputs"]["filename_prefix"] != second["38"]["inputs"]["filename_prefix"]


@pytest.mark.parametrize(
    "preset,precision",
    [
        ("preview", "0.26 MP - Preview"),
        ("small", "0.36 MP - Small"),
        ("standard", "0.52 MP - SD"),
        ("hd", "0.65 MP - Balanced"),
    ],
)
def test_minimax_h3_image_modes_patch_source_ratio_resolution(preset, precision):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_i2v")
    result = patcher.patch_workflow(
        "minimax_h3_i2v",
        workflow,
        {
            "prompt": "scene",
            "image": "first.png",
            "aspect_ratio": "source",
            "resolution_preset": preset,
            "width": 0,
            "height": 0,
            "frame_count": 124,
            "seed": 9,
        },
    )
    assert result["41"]["inputs"]["resolution_preset"] == precision
    assert result["30"]["inputs"]["width"] == ["41", 0]
    assert result["30"]["inputs"]["height"] == ["41", 1]


@pytest.mark.parametrize("field", ["model_name", "timeline_data", "lora_name", "steps"])
def test_minimax_h3_worker_rejects_execution_overrides(field):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="rejects"):
        patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene", field: "override"})
