import json
from pathlib import Path

import pytest

from scripts.build_minimax_h3_api_workflows import build
from src.workflow_mapping_validation import (
    resolve_workflow_filename,
    validate_workflow_directory,
)
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
TEN_EROS_BETA4_MODEL = "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4.safetensors"
TEN_EROS_BETA4_INT8_MODEL = (
    "MiniMaxH3/10Eros_Max_h3_TURBO-hybrid_beta4_int8_convrot.safetensors"
)
OFFICIAL_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
OFFICIAL_VIDEO_VAE = "MiniMaxH3/minimax_h3_video_vae_fp16.safetensors"


def test_minimax_h3_api_workflows_are_deterministic():
    validate_workflow_directory("workers/comfy_agent/workflows")
    for task_type, filename in TASKS.items():
        assert resolve_workflow_filename(task_type) == filename
        main = Path("workers/comfy_agent/workflows") / filename
        workflow = json.loads(main.read_text())
        assert workflow == build(task_type)
        assert workflow["1"]["inputs"]["unet_name"] == TEN_EROS_BETA4_MODEL
        assert "8" not in workflow
        assert "9" not in workflow
        assert "nodes" not in workflow
        if task_type == "minimax_h3_ref2v":
            assert workflow["2"]["inputs"] == {
                "model": ["1", 0],
                "attention": "pytorch attention",
            }
            assert workflow["3"]["inputs"] == {
                "model": ["2", 0],
                "shift_video": 12.0,
                "shift_audio": 7.0,
            }
            assert workflow["30"]["class_type"] == "MiniMaxH3ReferenceToVideo"
            assert workflow["30"]["inputs"]["ref_image_size"] == "match"
            assert workflow["26"]["class_type"] == "VHS_LoadVideo"
            assert workflow["33"]["inputs"]["sampler_name"] == "euler"
            assert workflow["34"] == {
                "inputs": {
                    "model": ["7", 0],
                    "scheduler": "simple",
                    "steps": 8,
                    "denoise": 1.0,
                },
                "class_type": "BasicScheduler",
            }
            continue
        assert workflow["2"] == {
            "inputs": {
                "model": ["1", 0],
                "attention": (
                    "pytorch attention"
                    if task_type == "minimax_h3_ref2v"
                    else "comfy kitchen attention"
                ),
            },
            "class_type": "ModelAttentionBackend",
        }
        assert workflow["3"]["inputs"] == {
            "model": ["2", 0],
            "shift_video": 12.0,
            "shift_audio": 7.0,
        }
        assert workflow["7"]["class_type"] == "ReservedVRAMSetter"
        assert workflow["30"]["class_type"] == "MiniMaxH3ImageToVideo"
        assert workflow["30"]["inputs"]["vae"] == ["5", 0]
        assert workflow["30"]["inputs"]["length"] == 124
        assert "audio_vae" not in workflow["30"]["inputs"]
        assert workflow["4"]["inputs"]["clip_name"] == OFFICIAL_CLIP
        assert workflow["5"]["inputs"]["vae_name"] == OFFICIAL_VIDEO_VAE
        assert workflow["32"]["inputs"]["model"] == ["7", 0]
        assert workflow["34"] == {
            "inputs": {
                "model": ["7", 0],
                "scheduler": "simple",
                "steps": 8,
                "denoise": 1.0,
            },
            "class_type": "BasicScheduler",
        }
        assert workflow["33"] == {
            "inputs": {"sampler_name": "euler"},
            "class_type": "KSamplerSelect",
        }
        assert not any(
            node.get("class_type")
            in {
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


@pytest.mark.parametrize(
    "params",
    [
        {"lora_strength": 1.0},
        {"lora_items": [{"name": "missing", "strength": 0.75}]},
        {"lora_items": [{"name": "deepthroat"}, {"name": "deepthroat"}]},
        {"addon_models": ["duplicate"]},
    ],
)
def test_minimax_h3_patcher_rejects_invalid_addon_overrides(params):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="MiniMax H3 addon"):
        patcher.patch_workflow(
            "minimax_h3_t2v", workflow, {"prompt": "scene", **params}
        )


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

    assert result["1"]["inputs"]["unet_name"] == TEN_EROS_BETA4_MODEL


def test_minimax_h3_patcher_without_addon_uses_10eros_beta4_native_turbo_path():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    patched = patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene"})
    assert not {"10", "11", "12", "13"} & patched.keys()
    assert "8" not in patched
    assert "9" not in patched
    assert patched["2"]["inputs"]["model"] == ["1", 0]
    assert patched["3"]["inputs"]["shift_video"] == 12.0
    assert patched["3"]["inputs"]["shift_audio"] == 7.0
    assert patched["33"]["inputs"]["sampler_name"] == "euler"
    assert patched["34"] == {
        "inputs": {
            "model": ["7", 0],
            "scheduler": "simple",
            "steps": 8,
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    }
    assert patched["1"]["inputs"]["unet_name"] == TEN_EROS_BETA4_MODEL
    assert patched["30"]["inputs"]["prompt"] == "scene"


@pytest.mark.parametrize(
    ("task_type", "params"),
    [
        (
            "minimax_h3_i2v",
            {"image": "first.png", "aspect_ratio": "source"},
        ),
        (
            "minimax_h3_ref2v",
            {"image": "subject.png", "image2": "reference.png"},
        ),
    ],
)
def test_minimax_h3_patcher_selects_approved_10eros_int8_main_model(task_type, params):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow(task_type)

    patched = patcher.patch_workflow(
        task_type,
        workflow,
        {"prompt": "scene", "main_model": "10eros_int8", **params},
    )

    assert patched["1"]["inputs"]["unet_name"] == TEN_EROS_BETA4_INT8_MODEL
    assert patched["2"]["inputs"]["model"] == ["1", 0]
    assert patched["33"]["inputs"]["sampler_name"] == "euler"
    assert patched["34"]["class_type"] == "BasicScheduler"
    assert patched["34"]["inputs"]["steps"] == 8
    if task_type == "minimax_h3_ref2v":
        assert patched["30"]["inputs"]["ref_image_size"] == "match"


def test_minimax_h3_patcher_keeps_10eros_ref2v_turbo_profile():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")

    patched = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {"prompt": "scene", "image": "subject.png", "image2": "reference.png"},
    )

    assert patched["1"]["inputs"]["unet_name"] == TEN_EROS_BETA4_MODEL
    assert patched["30"]["inputs"]["ref_image_size"] == "match"
    assert patched["3"]["inputs"]["shift_video"] == 12.0
    assert patched["3"]["inputs"]["shift_audio"] == 7.0
    assert patched["33"]["inputs"]["sampler_name"] == "euler"
    assert patched["34"] == {
        "inputs": {
            "model": ["7", 0],
            "scheduler": "simple",
            "steps": 8,
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    }


def test_minimax_h3_ref2v_maps_single_reference_audio_without_prompt_injection():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")

    patched = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {
            "prompt": "the character speaks softly",
            "image": "subject.png",
            "reference_audio": "voice.m4a",
        },
    )

    assert patched["25"] == {
        "inputs": {"audio": "voice.m4a"},
        "class_type": "LoadAudio",
    }
    assert patched["30"]["inputs"]["ref_audios.ref_audio_0"] == ["25", 0]
    assert patched["30"]["inputs"]["prompt"] == "the character speaks softly"


def test_minimax_h3_ref2v_without_reference_audio_prunes_audio_input_node():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")

    patched = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {"prompt": "scene", "image": "subject.png"},
    )

    assert "25" not in patched
    assert "ref_audios.ref_audio_0" not in patched["30"]["inputs"]


def test_minimax_h3_ref2v_maps_tail_video_frames_and_paired_audio():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")

    patched = patcher.patch_workflow(
        "minimax_h3_ref2v",
        workflow,
        {
            "prompt": "continue the movement",
            "reference_video": "previous-tail.mp4",
        },
    )

    assert patched["26"]["inputs"] == {
        "video": "previous-tail.mp4",
        "force_rate": 24,
        "custom_width": 0,
        "custom_height": 0,
        "frame_load_cap": 120,
        "skip_first_frames": 0,
        "select_every_nth": 1,
        "format": "None",
    }
    assert patched["30"]["inputs"]["ref_videos.ref_video_0"] == ["26", 0]
    assert patched["30"]["inputs"]["ref_video_audios.ref_video_audio_0"] == ["26", 2]
    assert patched["30"]["inputs"]["prompt"].startswith(
        "<Video 1> is the final five seconds of the previous segment."
    )


@pytest.mark.parametrize("retired", ["official", "official_ref2v_turbo"])
def test_minimax_h3_patcher_rejects_retired_official_profiles(retired):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_ref2v")

    with pytest.raises(ValueError, match="main model"):
        patcher.patch_workflow(
            "minimax_h3_ref2v",
            workflow,
            {
                "prompt": "scene",
                "main_model": retired,
                "image": "subject.png",
                "image2": "reference.png",
            },
        )


def test_minimax_h3_patcher_rejects_unknown_main_model():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_i2v")

    with pytest.raises(ValueError, match="main model"):
        patcher.patch_workflow(
            "minimax_h3_i2v",
            workflow,
            {
                "prompt": "scene",
                "image": "first.png",
                "aspect_ratio": "source",
                "main_model": "untrusted-checkpoint",
            },
        )


def test_minimax_h3_patcher_injects_only_the_four_approved_addons_in_order():
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    patched = patcher.patch_workflow(
        "minimax_h3_t2v",
        workflow,
        {
            "prompt": "scene",
            "lora_items": [
                {"name": "deepthroat"},
                {"name": "pov_missionary"},
                {"name": "footjob"},
                {"name": "cumshot"},
            ],
        },
    )
    assert patched["100"]["inputs"] == {
        "model": ["1", 0],
        "lora_name": "MiniMaxH3/deepthroat_v02.safetensors",
        "strength_model": 0.75,
    }
    assert patched["101"]["inputs"] == {
        "model": ["100", 0],
        "lora_name": "MiniMaxH3/H3_Mis_Insrt_v07.safetensors",
        "strength_model": 0.7,
    }
    assert patched["102"]["inputs"] == {
        "model": ["101", 0],
        "lora_name": "MiniMaxH3/H3_Footjob_TypeB_v1.safetensors",
        "strength_model": 0.5,
    }
    assert patched["103"]["inputs"] == {
        "model": ["102", 0],
        "lora_name": "MiniMaxH3/HMCumshot_V2.safetensors",
        "strength_model": 0.9,
    }
    assert patched["2"]["inputs"]["model"] == ["103", 0]
    assert patched["30"]["inputs"]["prompt"] == "fj., hmcumshot3, scene"


def test_minimax_h3_worker_forces_pytorch_attention_when_requested(monkeypatch):
    monkeypatch.setenv("MINIMAX_H3_FORCE_PYTORCH_ATTENTION", "true")
    workflow = json.loads(
        Path("workers/comfy_agent/workflows/MiniMax H3 I2V.api.json").read_text()
    )

    patch_minimax_h3_workflow(
        workflow,
        task_type="minimax_h3_i2v",
        params={"prompt": "scene", "image": "first.png"},
    )

    assert workflow["2"]["class_type"] == "ModelAttentionBackend"
    assert workflow["2"]["inputs"]["attention"] == "pytorch attention"


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
                {"name": "deepthroat", "strength": 0.75},
                {"name": "cumshot", "strength": 0.9},
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
    assert (
        first["40"]["inputs"]["filename_prefix"] == "minimax_h3_t2v_task_one_last_frame"
    )
    assert second["38"]["inputs"]["filename_prefix"] == "minimax_h3_t2v_task_two"
    assert (
        first["38"]["inputs"]["filename_prefix"]
        != second["38"]["inputs"]["filename_prefix"]
    )


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


@pytest.mark.parametrize(
    "field", ["model_name", "timeline_data", "sampler_name", "scheduler", "steps"]
)
def test_minimax_h3_worker_rejects_execution_overrides(field):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="rejects"):
        patcher.patch_workflow(
            "minimax_h3_t2v", workflow, {"prompt": "scene", field: "override"}
        )
