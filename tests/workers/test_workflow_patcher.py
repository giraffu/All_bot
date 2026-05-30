import json
from pathlib import Path

import pytest

from src.workflow_mapping_validation import WorkflowMappingValidationError
from workers.comfy_agent.workflow_patcher import WorkflowPatcher


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_workflow_patcher_validates_real_worker_workflows_on_init():
    patcher = WorkflowPatcher("/home/hfy/APP/All_bot/workers/comfy_agent/workflows")

    assert "img2img" in patcher.mappings
    assert patcher.load_workflow("img2img") is not None


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
                "length": "2586",
                "length_input": "value",
            }
        },
    )
    _write_json(
        workflow_dir / "WAN 2.2 i2v -AiO.json",
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
            "2542": {"inputs": {"clip_frames": ["2614", 0]}},
            "2557": {"inputs": {"value": True}},
            "2563": {"inputs": {"image": ["2574", 0]}},
            "2564": {"inputs": {"values.a": ["2563", 0]}},
            "2565": {"inputs": {"values.a": ["2563", 1]}},
            "2573": {"inputs": {"enabled": True}},
            "2574": {"inputs": {"original_images": ["2543", 1]}},
            "2575": {"inputs": {"image": ["2574", 0]}},
            "2584": {"inputs": {"enabled": True}},
            "2581": {"inputs": {"expression": "( a - 1 ) / b"}},
            "2586": {"inputs": {"value": 5}},
            "2621": {"inputs": {"precision_presets": "0.52 MP - SD"}},
            "2601": {"inputs": {"enabled": True}},
            "2602": {"inputs": {"enabled": True}},
            "2605": {"inputs": {"enabled": True}},
            "2612": {"inputs": {"switch": ["2557", 0]}},
            "2614": {"inputs": {"image_target": ["2612", 0]}},
            "2615": {"inputs": {"enabled": True}},
            "2700": {
                "inputs": {
                    "batch_index": 0,
                    "length": 1,
                    "image": ["2575", 0],
                },
                "class_type": "ImageFromBatch",
            },
            "28": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2",
                    "images": ["2575", 0],
                },
                "class_type": "VHS_VideoCombine",
            },
            "2501": {
                "inputs": {
                    "enabled": True,
                    "target_01": ["2503", 0],
                },
                "class_type": "DaSiWa_NodeStatusSwitch",
            },
            "2502": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2_mini",
                },
                "class_type": "VHS_VideoCombine",
            },
            "2503": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2_last_frame",
                    "images": ["2700", 0],
                },
                "class_type": "SaveImage",
            },
            "2547": {
                "inputs": {
                    "source": ["2552", 1],
                },
                "class_type": "PreviewAny",
            },
            "2548": {
                "inputs": {
                    "source": ["2549", 1],
                },
                "class_type": "PreviewAny",
            },
            "2587": {
                "inputs": {
                    "source": ["2580", 0],
                },
                "class_type": "PreviewAny",
            },
            "2589": {
                "inputs": {
                    "source": ["2581", 0],
                },
                "class_type": "PreviewAny",
            },
            "2623": {
                "inputs": {
                    "enabled": False,
                    "action": "mute",
                },
                "class_type": "DaSiWa_NodeStatusSwitch",
            },
            "2624": {
                "inputs": {
                    "enabled": False,
                    "action": "mute",
                },
                "class_type": "DaSiWa_NodeStatusSwitch",
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
            "length": 5,
            "seed": 42,
        },
    )

    assert patched["23"]["inputs"]["image"] == "start.png"
    assert patched["24"]["inputs"]["image"] == "start.png"
    assert "9" not in patched
    assert "2501" not in patched
    assert "2502" not in patched
    assert "2547" not in patched
    assert "2548" not in patched
    assert "2573" not in patched
    assert "2587" not in patched
    assert "2589" not in patched
    assert "2584" not in patched
    assert "2601" not in patched
    assert "2602" not in patched
    assert "2605" not in patched
    assert "2615" not in patched
    assert "2623" not in patched
    assert "2624" not in patched
    assert patched["2368"]["inputs"]["value"] == "demo"
    assert patched["2371"]["inputs"]["value"] == "bad"
    assert patched["2557"]["inputs"]["value"] is True
    assert patched["2621"]["inputs"]["precision_presets"] == "0.65 MP - Balanced"
    assert patched["2581"]["inputs"]["expression"] == "max(1, round(( a - 1 ) / b))"
    assert patched["2542"]["inputs"]["clip_frames"] == ["2612", 0]
    assert patched["2563"]["inputs"]["image"] == ["2612", 0]
    assert patched["2575"]["inputs"]["image"] == ["2612", 0]
    assert patched["28"]["inputs"]["images"] == ["2612", 0]
    assert patched["2700"]["inputs"]["image"] == ["2612", 0]
    assert patched["28"]["inputs"]["filename_prefix"] == "wan22_video_v2_42_video"
    assert patched["2503"]["inputs"]["filename_prefix"] == "wan22_video_v2_42_last_frame"


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
                "length": "2586",
                "length_input": "value",
            }
        },
    )
    _write_json(
        workflow_dir / "WAN 2.2 i2v -AiO.json",
        {
            "23": {"inputs": {"image": ""}},
            "24": {"inputs": {"image": ""}},
            "2368": {"inputs": {"value": ""}},
            "2371": {"inputs": {"value": ""}},
            "2542": {"inputs": {"clip_frames": ["2614", 0]}},
            "2557": {"inputs": {"value": True}},
            "2563": {"inputs": {"image": ["2574", 0]}},
            "2574": {"inputs": {"original_images": ["2543", 1]}},
            "2575": {"inputs": {"image": ["2574", 0]}},
            "2581": {"inputs": {"expression": "( a - 1 ) / b"}},
            "2586": {"inputs": {"value": 5}},
            "2612": {"inputs": {"switch": ["2557", 0]}},
            "2614": {"inputs": {"image_target": ["2612", 0]}},
            "28": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2",
                    "images": ["2575", 0],
                },
                "class_type": "VHS_VideoCombine",
            },
            "2503": {
                "inputs": {
                    "filename_prefix": "wan22_video_v2_last_frame",
                    "images": ["2700", 0],
                },
                "class_type": "SaveImage",
            },
            "2700": {
                "inputs": {
                    "batch_index": 0,
                    "length": 1,
                    "image": ["2575", 0],
                },
                "class_type": "ImageFromBatch",
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
    assert patched["2557"]["inputs"]["value"] is False
    assert patched["2542"]["inputs"]["clip_frames"] == ["2612", 0]
    assert patched["28"]["inputs"]["images"] == ["2612", 0]
    assert patched["2700"]["inputs"]["image"] == ["2612", 0]
    assert patched["28"]["inputs"]["filename_prefix"] == "wan22_video_v2_99_video"
    assert patched["2503"]["inputs"]["images"] == ["2700", 0]
