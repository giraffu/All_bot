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
