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
