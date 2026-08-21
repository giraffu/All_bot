import json
from pathlib import Path

import pytest

from scripts.build_minimax_h3_api_workflows import build
from src.workflow_mapping_validation import resolve_workflow_filename, validate_workflow_directory
from workers.comfy_agent.workflow_patcher import WorkflowPatcher
from workers.comfy_agent.workflow_task_patchers import (
    patch_minimax_h3_workflow,
)


TASKS = {
    "minimax_h3_t2v": "MiniMax H3 T2V.api.json",
    "minimax_h3_i2v": "MiniMax H3 I2V.api.json",
    "minimax_h3_flf2v": "MiniMax H3 FLF2V.api.json",
    "minimax_h3_ref2v": "MiniMax H3 REF2V.api.json",
}
TEN_EROS_BETA2_MODEL = "MiniMaxH3/10Eros_Max_h3_fl2va_beta2_pruned.safetensors"
OFFICIAL_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
OFFICIAL_VIDEO_VAE = "MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"
LIGHTX2V_LORA = "MiniMaxH3/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
NAUGHTYTIMES_LORA = "MiniMaxH3/NaughtyTimes_pruned_r256_v2.safetensors"
TURBO_REF2VA_MODEL = "MiniMaxH3/10Eros_Max_h3_TURBO_ref2va_beta2.safetensors"
REF2V_SIGMAS = "1.00, 0.94, 0.83, 0.72, 0.55, 0.30, 0.10, 0.00"


def test_minimax_h3_api_workflows_are_deterministic():
    validate_workflow_directory("workers/comfy_agent/workflows")
    for task_type, filename in TASKS.items():
        assert resolve_workflow_filename(task_type) == filename
        main = Path("workers/comfy_agent/workflows") / filename
        workflow = json.loads(main.read_text())
        assert workflow == build(task_type)
        expected_model = (
            TURBO_REF2VA_MODEL
            if task_type == "minimax_h3_ref2v"
            else TEN_EROS_BETA2_MODEL
        )
        assert workflow["1"]["inputs"]["unet_name"] == expected_model
        assert "nodes" not in workflow
        if task_type == "minimax_h3_ref2v":
            assert "8" not in workflow
            assert workflow["2"]["inputs"] == {
                "model": ["1", 0],
                "attention": "pytorch attention",
            }
            assert workflow["3"]["inputs"] == {
                "model": ["2", 0],
                "shift_video": 11.0,
                "shift_audio": 4.0,
            }
            assert workflow["30"]["class_type"] == "MiniMaxH3ReferenceToVideo"
            assert workflow["30"]["inputs"]["ref_image_size"] == "match"
            assert workflow["33"]["inputs"]["sampler_name"] == "er_sde"
            assert workflow["34"] == {
                "inputs": {"sigmas": REF2V_SIGMAS},
                "class_type": "ManualSigmas",
            }
            assert not any(
                node.get("class_type") == "BasicScheduler"
                for node in workflow.values()
            )
            continue
        assert workflow["8"]["inputs"] == {
            "model": ["1", 0],
            "lora_name": LIGHTX2V_LORA,
            "strength_model": 1.0,
        }
        assert workflow["2"] == {
            "inputs": {"model": ["8", 0], "attention": "comfy kitchen attention"},
            "class_type": "ModelAttentionBackend",
        }
        assert "9" not in workflow
        assert workflow["3"]["inputs"] == {
            "model": ["2", 0],
            "shift_video": 12.0,
            "shift_audio": 3.0,
        }
        assert workflow["7"]["class_type"] == "ReservedVRAMSetter"
        assert workflow["30"]["class_type"] == "MiniMaxH3ImageToVideo"
        assert workflow["30"]["inputs"]["vae"] == ["5", 0]
        assert workflow["30"]["inputs"]["length"] == 124
        assert "audio_vae" not in workflow["30"]["inputs"]
        assert workflow["4"]["inputs"]["clip_name"] == OFFICIAL_CLIP
        assert workflow["5"]["inputs"]["vae_name"] == OFFICIAL_VIDEO_VAE
        assert workflow["32"]["inputs"]["model"] == ["7", 0]
        assert workflow["34"]["inputs"]["model"] == ["7", 0]
        assert workflow["34"]["inputs"]["steps"] == 8
        assert workflow["33"] == {
            "inputs": {"sampler_name": "euler"},
            "class_type": "KSamplerSelect",
        }
        assert not any(
            node.get("class_type") in {
                "MiniMaxH3MemoryEfficientSageAttentionPatch",
                "MiniMaxH3TurboSampler",
                "MiniMaxH3UnifiedToVideo",
            }
            for node in workflow.values()
        )
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


@pytest.mark.parametrize("params", [
    {"lora_strength": 1.0},
    {"lora_items": [{"name": "missing", "strength": 0.75}]},
    {"lora_items": [{"name": "penis"}, {"name": "penis"}]},
    {"addon_models": ["duplicate"]},
])
def test_minimax_h3_patcher_rejects_invalid_addon_overrides(params):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="MiniMax H3 addon"):
        patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene", **params})


def test_minimax_h3_patcher_tolerates_legacy_empty_addon_placeholders():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")

    result = patcher.patch_workflow(
        "minimax_h3_t2v",
        workflow,
        {
            "prompt": "scene",
            "lora_items": [],
            "lora_name": None,
            "lora_strength": None,
            "addon_models": [],
        },
    )

    assert result["1"]["inputs"]["unet_name"] == TEN_EROS_BETA2_MODEL


def test_minimax_h3_patcher_without_addon_keeps_10eros_plus_lightx2v_only():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    patched = patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene"})
    assert not {"10", "11", "12", "13"} & patched.keys()
    assert patched["8"]["inputs"]["lora_name"] == LIGHTX2V_LORA
    assert "9" not in patched
    assert patched["2"]["inputs"]["model"] == ["8", 0]
    assert patched["1"]["inputs"]["unet_name"] == TEN_EROS_BETA2_MODEL
    assert patched["30"]["inputs"]["prompt"] == "scene"


def test_minimax_h3_patcher_injects_selected_addons_after_lightx2v_in_order():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    patched = patcher.patch_workflow(
        "minimax_h3_t2v",
        workflow,
        {
            "prompt": "two adults move in a bedroom",
            "lora_items": [
                {"name": "naughty_times", "strength": 0.8},
                {"name": "sex_pose", "strength": 0.45},
                {"name": "pussy", "strength": 0.3},
            ],
        },
    )
    assert patched["100"]["inputs"] == {
        "model": ["8", 0],
        "lora_name": NAUGHTYTIMES_LORA,
        "strength_model": 0.8,
    }
    assert patched["101"]["inputs"] == {
        "model": ["100", 0],
        "lora_name": "MiniMaxH3/HMNSFW_AIO_V2.safetensors",
        "strength_model": 0.45,
    }
    assert patched["102"]["inputs"] == {
        "model": ["101", 0],
        "lora_name": "MiniMaxH3/hmpussy_v6_epoch30.safetensors",
        "strength_model": 0.3,
    }
    assert patched["2"]["inputs"]["model"] == ["102", 0]
    assert patched["30"]["inputs"]["prompt"] == (
        "hmmotion, Vagina, two adults move in a bedroom"
    )


def test_minimax_h3_worker_injects_addon_chain():
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 T2V.api.json").read_text()
    )
    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_t2v",
        params={
            "prompt": "scene",
            "lora_items": [{"name": "breasts", "strength": 1.2}],
        },
    )
    assert workflow["100"]["inputs"]["model"] == ["8", 0]
    assert workflow["100"]["inputs"]["strength_model"] == 1.2
    assert workflow["2"]["inputs"]["model"] == ["100", 0]
    assert workflow["30"]["inputs"]["prompt"] == "HMBreasts, scene"


def test_minimax_h3_worker_injects_motion_booster_trigger_but_not_mystic_trigger():
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 T2V.api.json").read_text()
    )
    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_t2v",
        params={
            "prompt": "scene",
            "lora_items": [
                {"name": "motion_booster", "strength": 0.7},
                {"name": "mystic_xxx", "strength": 0.75},
            ],
        },
    )

    assert workflow["100"]["inputs"] == {
        "model": ["8", 0],
        "lora_name": "MiniMaxH3/H3_Motion_BoosterV2.safetensors",
        "strength_model": 0.7,
    }
    assert workflow["101"]["inputs"] == {
        "model": ["100", 0],
        "lora_name": "MiniMaxH3/MysticXXX_MMH3-V2.safetensors",
        "strength_model": 0.75,
    }
    assert workflow["2"]["inputs"]["model"] == ["101", 0]
    assert workflow["30"]["inputs"]["prompt"] == "dynv2, scene"


def test_minimax_h3_worker_chains_new_action_loras_and_injects_declared_triggers():
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 T2V.api.json").read_text()
    )
    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_t2v",
        params={
            "prompt": "scene",
            "lora_items": [
                {"name": "breast_play"},
                {"name": "innie"},
                {"name": "deepthroat"},
                {"name": "pov_missionary"},
                {"name": "footjob"},
            ],
        },
    )

    assert [workflow[str(node)]["inputs"]["lora_name"] for node in range(100, 105)] == [
        "MiniMaxH3/breastplayjiggle_h3_v1.safetensors",
        "MiniMaxH3/HMInnie_v1_e50.safetensors",
        "MiniMaxH3/deepthroat_v02.safetensors",
        "MiniMaxH3/H3_Mis_Insrt_v07.safetensors",
        "MiniMaxH3/H3_Footjob_TypeB_v1.safetensors",
    ]
    assert [workflow[str(node)]["inputs"]["strength_model"] for node in range(100, 105)] == [
        0.75,
        0.8,
        0.75,
        0.7,
        0.5,
    ]
    assert workflow["2"]["inputs"]["model"] == ["104", 0]
    assert workflow["30"]["inputs"]["prompt"] == "inniepussy, fj., scene"


def test_minimax_h3_worker_chains_new_stills_and_titjob_loras_with_triggers():
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 T2V.api.json").read_text()
    )
    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_t2v",
        params={
            "prompt": "scene",
            "lora_items": [
                {"name": "pussy_stills_v1"},
                {"name": "titjob"},
            ],
        },
    )

    assert workflow["100"]["inputs"] == {
        "model": ["8", 0],
        "lora_name": "MiniMaxH3/Vagina_minimax-h3_epoch20.safetensors",
        "strength_model": 0.35,
    }
    assert workflow["101"]["inputs"] == {
        "model": ["100", 0],
        "lora_name": "MiniMaxH3/Titjob_Titfuck_V1-MiniMaxh3_ComfyTinker.safetensors",
        "strength_model": 0.75,
    }
    assert workflow["2"]["inputs"]["model"] == ["101", 0]
    assert workflow["30"]["inputs"]["prompt"] == "pussy, titjob, scene"


def test_minimax_h3_worker_uses_prompt_without_trigger_injection():
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 T2V.api.json").read_text()
    )
    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_t2v",
        params={"prompt": "scene", "frame_count": 243},
    )
    assert workflow["30"]["inputs"]["prompt"] == "scene"
    assert workflow["30"]["inputs"]["length"] == 243


def test_minimax_h3_ref2v_patcher_orders_five_images_and_addons_without_lightx2v():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")
    images = [f"ref-{index}.png" for index in range(1, 6)]
    result = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {
            "prompt": "<Picture 1> walks beside <Picture 2>",
            "image": images[0],
            "image2": images[1],
            "image3": images[2],
            "image4": images[3],
            "image5": images[4],
            "duration": 10,
            "lora_items": [
                {"name": "motion_booster", "strength": 0.7},
                {"name": "pussy", "strength": 0.35},
            ],
        },
    )

    assert result["100"]["inputs"]["model"] == ["1", 0]
    assert result["101"]["inputs"]["model"] == ["100", 0]
    assert result["2"]["inputs"]["model"] == ["101", 0]
    assert "8" not in result
    assert result["30"]["inputs"]["length"] == 243
    for index, image in enumerate(images):
        node_id = str(20 + index)
        assert result[node_id]["inputs"]["image"] == image
        assert result["30"]["inputs"][f"ref_images.ref_image_{index}"] == [node_id, 0]


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
    assert result["30"]["inputs"]["length"] == 124


@pytest.mark.parametrize("field", ["model_name", "timeline_data", "sampler_name", "scheduler", "steps"])
def test_minimax_h3_worker_rejects_execution_overrides(field):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="rejects"):
        patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene", field: "override"})
