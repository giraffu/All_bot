import json
from pathlib import Path

import pytest

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
        assert "nodes" not in workflow
        assert workflow["3"]["inputs"] == {"model": ["2", 0], "shift_video": 11.0, "shift_audio": 4.0}
        assert workflow["34"]["inputs"]["steps"] == 25
        assert workflow["33"]["inputs"]["sampler_name"] == "res_multistep"
        assert workflow["38"]["inputs"]["audio"] == ["37", 0]
        assert workflow["40"]["class_type"] == "SaveImage"
        assert workflow["39"]["inputs"]["batch_index"] == 4095


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
    assert result["30"]["inputs"]["prompt"].startswith("<Picture 1>: adult woman\n<Picture 2>: adult man")


@pytest.mark.parametrize("field", ["model_name", "timeline_data", "lora_name", "steps"])
def test_minimax_h3_worker_rejects_execution_overrides(field):
    patcher = WorkflowPatcher("workers/comfy_agent/workflows")
    workflow = patcher.load_workflow("minimax_h3_t2v")
    with pytest.raises(ValueError, match="rejects"):
        patcher.patch_workflow("minimax_h3_t2v", workflow, {"prompt": "scene", field: "override"})
