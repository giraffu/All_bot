import json
from pathlib import Path

import pytest

from src.workflow_mapping_validation import (
    WORKFLOW_FILENAME_OVERRIDES_ENV,
    WorkflowMappingValidationError,
    resolve_workflow_filename,
    validate_workflow_directory,
)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_workflow_filename_uses_env_override(monkeypatch):
    monkeypatch.setenv(
        WORKFLOW_FILENAME_OVERRIDES_ENV,
        '{"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json"}',
    )

    assert (
        resolve_workflow_filename("t2i-pornmaster-turbo")
        == "txt2img_from_i2i_pro.json"
    )
    assert resolve_workflow_filename("i2i_pro") == "i2i_pro.json"


def test_validate_workflow_directory_accepts_task_type_workflow_override(
    monkeypatch, tmp_path
):
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    _write_json(
        workflow_dir / "mappings.json",
        {
            "t2i-pornmaster-turbo": {
                "prompt": "90",
                "prompt_input": "text",
            }
        },
    )
    _write_json(
        workflow_dir / "txt2img_from_i2i_pro.json",
        {
            "90": {
                "inputs": {
                    "text": "",
                }
            }
        },
    )
    monkeypatch.setenv(
        WORKFLOW_FILENAME_OVERRIDES_ENV,
        '{"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json"}',
    )

    mappings = validate_workflow_directory(str(workflow_dir))

    assert "t2i-pornmaster-turbo" in mappings


@pytest.mark.parametrize(
    "raw_override",
    [
        "[]",
        '{"t2i-pornmaster-turbo":""}',
        '{"t2i-pornmaster-turbo":"/tmp/workflow.json"}',
        '{"t2i-pornmaster-turbo":"../workflow.json"}',
    ],
)
def test_invalid_workflow_override_fails_fast(monkeypatch, raw_override):
    monkeypatch.setenv(WORKFLOW_FILENAME_OVERRIDES_ENV, raw_override)

    with pytest.raises(WorkflowMappingValidationError):
        resolve_workflow_filename("t2i-pornmaster-turbo")
