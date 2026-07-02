import json
from pathlib import Path

import pytest

from src.domain_config.scail2_video import (
    SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT,
    SCAIL2_VIDEO_REPLACEMENT_DEFAULT_POSITIVE_PROMPT,
)
from src.workflow_mapping_validation import WorkflowMappingValidationError
from workers.comfy_agent.workflow_patcher import WorkflowPatcher


WORKER_WORKFLOW_DIR = "/home/hfy/APP/All_bot/workers/comfy_agent/workflows"


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_workflow_patcher_validates_real_worker_workflows_on_init():
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)

    assert "img2img" in patcher.mappings
    assert patcher.load_workflow("img2img") is not None


@pytest.mark.parametrize(
    ("task_type", "replacement_mode", "duration", "frame_count"),
    [
        ("scail2_action_transfer", False, 8, 129),
        ("scail2_action_transfer_long", False, 10, 161),
        ("scail2_action_transfer_long", False, 15, 241),
        ("scail2_action_transfer_long", False, 20, 321),
        ("scail2_video_replacement", True, 8, 129),
        ("scail2_face_swap_v2", True, 8, 129),
    ],
)
def test_workflow_patcher_overrides_scail2_runtime_parameters(
    task_type,
    replacement_mode,
    duration,
    frame_count,
):
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)
    workflow = patcher.load_workflow(task_type)

    patched = patcher.patch_workflow(
        task_type,
        workflow,
        {
            "image": "reference.png",
            "video": "motion.mp4",
            "prompt": "dance naturally",
            "negative_prompt": "blur",
            "length": duration,
        },
    )

    assert patched["58"]["inputs"]["image"] == "reference.png"
    assert patched["113"]["inputs"]["video"] == "motion.mp4"
    assert patched["113"]["inputs"]["force_rate"] == 16
    assert patched["113"]["inputs"]["frame_load_cap"] == frame_count
    assert patched["113"]["inputs"]["skip_first_frames"] == 0
    if task_type == "scail2_face_swap_v2":
        prompt = patched["6"]["inputs"]["text"]
        assert prompt.startswith(SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT)
        assert "Additional user guidance: dance naturally" in prompt
    else:
        assert patched["6"]["inputs"]["text"] == "dance naturally"
    assert patched["7"]["inputs"]["text"] == "blur"
    assert patched["101"]["inputs"]["width"] == 512
    assert patched["101"]["inputs"]["height"] == 896
    assert patched["101"]["inputs"]["length"] == frame_count
    assert patched["101"]["inputs"]["replacement_mode"] is replacement_mode
    assert patched["107"]["inputs"]["replacement_mode"] is replacement_mode
    assert patched["49"]["inputs"]["frame_rate"] == 16
    assert patched["49"]["inputs"]["filename_prefix"].startswith(f"{task_type}_")
    if task_type == "scail2_action_transfer_long":
        assert patched["124"]["inputs"]["freenoise"] is True


def test_workflow_patcher_uses_scail2_default_prompt_when_empty():
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)
    workflow = patcher.load_workflow("scail2_video_replacement")

    patched = patcher.patch_workflow(
        "scail2_video_replacement",
        workflow,
        {
            "image": "reference.png",
            "video": "motion.mp4",
            "prompt": "",
            "length": 5,
        },
    )

    assert patched["6"]["inputs"]["text"] == SCAIL2_VIDEO_REPLACEMENT_DEFAULT_POSITIVE_PROMPT


def test_workflow_patcher_preserves_faceswap_default_constraints_with_user_prompt():
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)
    workflow = patcher.load_workflow("scail2_face_swap_v2")

    patched = patcher.patch_workflow(
        "scail2_face_swap_v2",
        workflow,
        {
            "image": "reference.png",
            "video": "motion.mp4",
            "prompt": "替换",
            "length": 5,
        },
    )

    prompt = patched["6"]["inputs"]["text"]
    assert prompt.startswith(SCAIL2_FACE_SWAP_V2_DEFAULT_POSITIVE_PROMPT)
    assert "Additional user guidance: 替换" in prompt


def test_workflow_patcher_rejects_missing_mapped_input(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "face_swap": {
                "face_image": "2",
                "face_image_input": "missing_input",
            }
        },
    )
    _write_json(
        workflow_dir / "face_swap.json",
        {
            "2": {
                "inputs": {
                    "image": "foo.png",
                }
            }
        },
    )

    with pytest.raises(WorkflowMappingValidationError, match="missing_input"):
        WorkflowPatcher(str(workflow_dir))


def test_workflow_patcher_strips_ltx_video_optional_lora_node_when_unset(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(workflow_dir / "LTX 2.3 I2V 6.1.json", {
        "8": {
            "inputs": {
                "model": ["256", 0],
            }
        },
        "256": {
            "inputs": {
                "model": ["191", 0],
                "clip": ["189", 0],
            },
            "class_type": "Power Lora Loader (rgthree)",
        },
    })

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("ltx_video")

    patched = patcher.patch_workflow("ltx_video", workflow, {"prompt": "demo"})

    assert "256" not in patched
    assert patched["8"]["inputs"]["model"] == ["191", 0]


def test_workflow_patcher_injects_ltx_video_optional_lora_when_present(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(workflow_dir / "LTX 2.3 I2V 6.1.json", {
        "8": {
            "inputs": {
                "model": ["256", 0],
            }
        },
        "256": {
            "inputs": {
                "model": ["191", 0],
                "clip": ["189", 0],
            },
            "class_type": "Power Lora Loader (rgthree)",
        },
    })

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("ltx_video")

    patched = patcher.patch_workflow(
        "ltx_video",
        workflow,
        {
            "prompt": "demo",
            "lora_name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "lora_strength": 0.8,
        },
    )

    assert patched["256"]["inputs"]["lora_1"] == {
        "on": True,
        "lora": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
        "strength": 0.8,
    }
    assert patched["256"]["inputs"]["model"] == ["191", 0]
    assert patched["256"]["inputs"]["clip"] == ["189", 0]


def test_workflow_patcher_injects_multiple_ltx_video_loras_from_lora_items(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(workflow_dir / "LTX 2.3 I2V 6.1.json", {
        "8": {
            "inputs": {
                "model": ["256", 0],
            }
        },
        "256": {
            "inputs": {
                "model": ["191", 0],
                "clip": ["189", 0],
                "lora_9": {"on": False, "lora": "stale", "strength": 1.0},
            },
            "class_type": "Power Lora Loader (rgthree)",
        },
    })

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("ltx_video")

    patched = patcher.patch_workflow(
        "ltx_video",
        workflow,
        {
            "prompt": "demo",
            "lora_items": [
                {
                    "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                    "strength": 0.8,
                },
                {
                    "name": "ltx2.3/SynthPussy_01_rank32.safetensors",
                    "strength": 0.75,
                },
            ],
        },
    )

    assert patched["256"]["inputs"]["lora_1"] == {
        "on": True,
        "lora": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
        "strength": 0.8,
    }
    assert patched["256"]["inputs"]["lora_2"] == {
        "on": True,
        "lora": "ltx2.3/SynthPussy_01_rank32.safetensors",
        "strength": 0.75,
    }
    assert "lora_9" not in patched["256"]["inputs"]


def test_workflow_patcher_patches_real_ltx_flf2v_workflow():
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)
    workflow = patcher.load_workflow("ltx_video_flf2v")

    patched = patcher.patch_workflow(
        "ltx_video_flf2v",
        workflow,
        {
            "image": "start.png",
            "end_image": "end.png",
            "prompt": "cinematic transition",
            "length": 10,
            "width": 1280,
            "height": 704,
            "seed": 123,
        },
    )

    assert patched["15"]["inputs"]["image"] == "start.png"
    assert patched["16"]["inputs"]["image"] == "end.png"
    assert patched["26:297"]["inputs"]["num_images"] == "2"
    assert patched["26:297"]["inputs"]["num_images.image_2"] == ["26:313", 0]
    assert patched["26:297"]["inputs"]["num_images.index_2"] == ["26:315", 0]
    assert patched["26:312"]["inputs"]["num_images"] == "2"
    assert patched["902"]["inputs"]["filename_prefix"] == "ltx_video_flf2v_123_last_frame"
    assert patched["61"]["inputs"]["filename_prefix"] == "ltx_video_flf2v_123_61"


def test_workflow_patcher_patches_real_ltx_v2v_audio_workflow():
    patcher = WorkflowPatcher(WORKER_WORKFLOW_DIR)
    workflow = patcher.load_workflow("ltx_video_v2v_audio")

    patched = patcher.patch_workflow(
        "ltx_video_v2v_audio",
        workflow,
        {
            "video": "input.mp4",
            "prompt": "say the line clearly",
            "length": 15,
            "width": 1280,
            "height": 704,
            "seed": 456,
        },
    )

    assert patched["900"]["inputs"]["video"] == "input.mp4"
    assert patched["900"]["inputs"]["force_rate"] == 24
    assert patched["900"]["inputs"]["frame_load_cap"] == 361
    assert patched["900"]["inputs"]["skip_first_frames"] == 0
    assert patched["900"]["inputs"]["select_every_nth"] == 1
    assert patched["902"]["inputs"]["filename_prefix"] == "ltx_video_v2v_audio_456_last_frame"
    assert patched["61"]["inputs"]["filename_prefix"] == "ltx_video_v2v_audio_456_61"


def test_workflow_patcher_patches_wan22_video_v2_boolean_gates_and_prefixes(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "wan22_video_v2": {
                "image": "23",
                "image_input": "image",
                "end_image": "24",
                "end_image_input": "image",
                "prompt": "2368",
                "prompt_input": "value",
                "negative_prompt": "2371",
                "negative_prompt_input": "value",
            }
        },
    )
    _write_json(
        workflow_dir / "Wan22AioV82.json",
        {
            "9": {
                "inputs": {
                    "filenames": ["28", 0],
                },
                "class_type": "VHS_PruneOutputs",
            },
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2368": {"inputs": {"value": ""}},
            "2371": {"inputs": {"value": ""}},
            "2558": {"inputs": {"value": False}},
            "2578": {"inputs": {"value": 5}},
            "2612": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2623": {"inputs": {"expression": "( a - 1 ) / b"}},
            "2575": {"inputs": {"images": ["2603", 0]}},
            "2607": {
                "inputs": {
                    "batch_index": 0,
                    "length": 1,
                    "image": ["2603", 0],
                },
                "class_type": "ImageFromBatch",
            },
            "28": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2",
                    "images": ["2603", 0],
                },
                "class_type": "VHS_VideoCombine",
            },
            "265": {
                "inputs": {
                    "ckpt_name": "rife49",
                    "multiplier": 4,
                    "ensemble": False,
                    "images": ["2603", 0],
                },
                "class_type": "FL_RIFE",
            },
            "2503": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2_last_frame",
                    "images": ["2607", 0],
                },
                "class_type": "SaveImage",
            },
        },
    )

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("wan22_video_v2")

    patched = patcher.patch_workflow(
        "wan22_video_v2",
        workflow,
        {
            "image": "start.png",
            "prompt": "demo",
            "negative_prompt": "bad",
            "use_end_frame": False,
            "resolution_preset": "hd",
            "length": 8,
            "seed": 42,
        },
    )

    assert patched["23"]["inputs"]["image"] == "start.png"
    assert patched["24"]["inputs"]["image"] == "start.png"
    assert "9" not in patched
    assert patched["2368"]["inputs"]["value"] == "demo"
    assert patched["2371"]["inputs"]["value"] == "bad"
    assert patched["2558"]["inputs"]["value"] is True
    assert patched["2578"]["inputs"]["value"] == 8
    assert patched["2612"]["inputs"]["precision_presets"] == "0.65 MP - Balanced"
    assert patched["2612"]["inputs"]["resolution_preset"] == "0.65 MP - Balanced"
    assert patched["2612"]["inputs"]["swap_aspect_when_not_image"] is False
    assert patched["2612"]["inputs"]["aspect_preset_when_not_image"] == "9:16 - Social"
    assert patched["2612"]["inputs"]["custom_aspect_width"] == 16
    assert patched["2612"]["inputs"]["custom_aspect_height"] == 9
    assert patched["2623"]["inputs"]["expression"] == "max(1, round(( a - 1 ) / b))"
    assert patched["265"]["inputs"]["images"] == ["2603", 0]
    assert patched["2575"]["inputs"]["images"] == ["265", 0]
    assert patched["28"]["inputs"]["images"] == ["265", 0]
    assert patched["2607"]["inputs"]["batch_index"] == 4095
    assert patched["2607"]["inputs"]["image"] == ["265", 0]
    assert patched["28"]["inputs"]["filename_prefix"] == "wan22_video_v2_42_video"
    assert patched["2503"]["inputs"]["filename_prefix"] == "wan22_video_v2_42_last_frame"
    assert patched["2503"]["inputs"]["images"] == ["2607", 0]


def test_workflow_patcher_patches_wan22_video_v2_preview_resolution(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "wan22_video_v2": {
                "image": "23",
                "image_input": "image",
            }
        },
    )
    _write_json(
        workflow_dir / "Wan22AioV82.json",
        {
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2558": {"inputs": {"value": False}},
            "2578": {"inputs": {"value": 5}},
            "2607": {"inputs": {"batch_index": 0, "length": 1, "image": ["2603", 0]}},
            "2612": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2623": {"inputs": {"expression": "( a - 1 ) / b"}},
            "28": {"inputs": {"filename_prefix": "wan22_video_v2", "images": ["2603", 0]}},
            "2503": {"inputs": {"filename_prefix": "wan22_video_v2_last_frame", "images": ["2607", 0]}},
        },
    )

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("wan22_video_v2")

    patched = patcher.patch_workflow(
        "wan22_video_v2",
        workflow,
        {
            "image": "start.png",
            "resolution_preset": "preview",
            "seed": 77,
        },
    )

    assert patched["2612"]["inputs"]["precision_presets"] == "0.26 MP - Preview"


def test_workflow_patcher_patches_wan22_video_v2_small_resolution(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "wan22_video_v2": {
                "image": "23",
                "image_input": "image",
            }
        },
    )
    _write_json(
        workflow_dir / "Wan22AioV82.json",
        {
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2558": {"inputs": {"value": False}},
            "2578": {"inputs": {"value": 5}},
            "2607": {"inputs": {"batch_index": 0, "length": 1, "image": ["2603", 0]}},
            "2612": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2623": {"inputs": {"expression": "( a - 1 ) / b"}},
            "28": {"inputs": {"filename_prefix": "wan22_video_v2", "images": ["2603", 0]}},
            "2503": {"inputs": {"filename_prefix": "wan22_video_v2_last_frame", "images": ["2607", 0]}},
        },
    )

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("wan22_video_v2")

    patched = patcher.patch_workflow(
        "wan22_video_v2",
        workflow,
        {
            "image": "start.png",
            "resolution_preset": "small",
            "seed": 77,
        },
    )

    assert patched["2612"]["inputs"]["precision_presets"] == "0.36 MP - Small"


def test_workflow_patcher_injects_legacy_image_to_video_lora_and_model_profile(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "image_to_video": {
                "image": "23",
                "image_input": "image",
                "prompt": "2368",
                "prompt_input": "value",
            },
            "wan22_video_v2": {
                "image": "23",
                "image_input": "image",
                "prompt": "2368",
                "prompt_input": "value",
            },
        },
    )
    _write_json(
        workflow_dir / "Wan22AioV82.json",
        {
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2368": {"inputs": {"value": ""}},
            "2371": {"inputs": {"value": ""}},
            "2558": {"inputs": {"value": False}},
            "2578": {"inputs": {"value": 5}},
            "2607": {"inputs": {"batch_index": 0, "length": 1, "image": ["2603", 0]}},
            "2612": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2623": {"inputs": {"expression": "( a - 1 ) / b"}},
            "2616": {"inputs": {"unet_name": "stale-high.safetensors"}},
            "2617": {"inputs": {"unet_name": "stale-low.safetensors"}},
            "26": {
                "inputs": {
                    "model": ["2569", 0],
                    "clip": ["2529", 0],
                    "lora_9": {"on": True, "lora": "stale", "strength": 1},
                },
                "class_type": "Power Lora Loader (rgthree)",
            },
            "18": {
                "inputs": {
                    "model": ["2560", 0],
                    "clip": ["2529", 0],
                    "lora_9": {"on": True, "lora": "stale", "strength": 1},
                },
                "class_type": "Power Lora Loader (rgthree)",
            },
            "28": {"inputs": {"filename_prefix": "wan22_video_v2", "images": ["2603", 0]}},
            "2503": {"inputs": {"filename_prefix": "wan22_video_v2_last_frame", "images": ["2607", 0]}},
        },
    )

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("image_to_video")

    patched = patcher.patch_workflow(
        "image_to_video",
        workflow,
        {
            "image": "start.png",
            "prompt": "demo",
            "lora_name": "BreastGrow",
            "resolution_preset": "standard",
            "length": 10,
            "seed": 77,
        },
    )

    assert patched["2616"]["inputs"]["unet_name"] == (
        "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8H.safetensors"
    )
    assert patched["2617"]["inputs"]["unet_name"] == (
        "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2FP8L.safetensors"
    )
    assert patched["26"]["inputs"]["lora_1"] == {
        "on": True,
        "lora": "BreastGrow_high_noise.safetensors",
        "strength": 1,
    }
    assert patched["18"]["inputs"]["lora_1"] == {
        "on": True,
        "lora": "BreastGrow_low_noise.safetensors",
        "strength": 1,
    }
    assert patched["2578"]["inputs"]["value"] == 10
    assert "lora_9" not in patched["26"]["inputs"]
    assert "lora_9" not in patched["18"]["inputs"]

    patched_v2 = patcher.patch_workflow(
        "wan22_video_v2",
        workflow,
        {
            "image": "start.png",
            "prompt": "demo",
            "lora_name": "BreastGrow",
            "resolution_preset": "standard",
            "seed": 78,
        },
    )

    assert patched_v2["2616"]["inputs"]["unet_name"] == (
        "DasiwaWAN22I2V14BLightspeed_snatchkissHighV11.safetensors"
    )
    assert patched_v2["2617"]["inputs"]["unet_name"] == (
        "DasiwaWAN22I2V14BLightspeed_snatchkissLowV11.safetensors"
    )
    assert "lora_1" not in patched_v2["26"]["inputs"]
    assert "lora_1" not in patched_v2["18"]["inputs"]
    assert "lora_9" not in patched_v2["26"]["inputs"]
    assert "lora_9" not in patched_v2["18"]["inputs"]


def test_workflow_patcher_strips_wan22_video_v2_last_frame_branch_when_disabled(tmp_path):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()

    _write_json(
        workflow_dir / "mappings.json",
        {
            "wan22_video_v2": {
                "image": "23",
                "image_input": "image",
                "end_image": "24",
                "end_image_input": "image",
                "prompt": "2368",
                "prompt_input": "value",
                "negative_prompt": "2371",
                "negative_prompt_input": "value",
            }
        },
    )
    _write_json(
        workflow_dir / "Wan22AioV82.json",
        {
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2368": {"inputs": {"value": ""}},
            "2371": {"inputs": {"value": ""}},
            "2558": {"inputs": {"value": False}},
            "2578": {"inputs": {"value": 5}},
            "2575": {"inputs": {"images": ["2603", 0]}},
            "2607": {
                "inputs": {
                    "batch_index": 0,
                    "length": 1,
                    "image": ["2603", 0],
                },
                "class_type": "ImageFromBatch",
            },
            "2612": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2623": {"inputs": {"expression": "( a - 1 ) / b"}},
            "28": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2",
                    "images": ["2603", 0],
                },
                "class_type": "VHS_VideoCombine",
            },
            "265": {
                "inputs": {
                    "ckpt_name": "rife49",
                    "multiplier": 4,
                    "ensemble": False,
                    "images": ["2603", 0],
                },
                "class_type": "FL_RIFE",
            },
            "2503": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2_last_frame",
                    "images": ["2607", 0],
                },
                "class_type": "SaveImage",
            },
        },
    )

    patcher = WorkflowPatcher(str(workflow_dir))
    workflow = patcher.load_workflow("wan22_video_v2")

    patched = patcher.patch_workflow(
        "wan22_video_v2",
        workflow,
        {
            "image": "start.png",
            "end_image": "end.png",
            "prompt": "demo",
            "negative_prompt": "bad",
            "use_end_frame": True,
            "length": 5,
            "seed": 99,
        },
    )

    assert patched["24"]["inputs"]["image"] == "end.png"
    assert patched["2558"]["inputs"]["value"] is False
    assert patched["2575"]["inputs"]["images"] == ["265", 0]
    assert patched["28"]["inputs"]["images"] == ["265", 0]
    assert patched["2607"]["inputs"]["image"] == ["265", 0]
    assert patched["28"]["inputs"]["filename_prefix"] == "wan22_video_v2_99_video"
    assert patched["2503"]["inputs"]["images"] == ["2607", 0]
