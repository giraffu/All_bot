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


@pytest.mark.parametrize("task_type", ["video_insert", "video_edit"])
def test_legacy_video_task_types_resolve_to_wan22_aio_workflow(task_type):
    assert resolve_workflow_filename(task_type) == "Wan22AioV82.json"


@pytest.mark.parametrize(
    ("task_type", "filename"),
    [
        ("ltx_video_flf2v", "LTX 2.3 FLF2V 6.1.json"),
        ("ltx_video_v2v_audio", "LTX 2.3 V2V Audio 6.1.json"),
        ("scail2_action_transfer", "SCAIL-2_Animation_multi-char_audio.api.json"),
        (
            "scail2_action_transfer_long",
            "SCAIL-2_Animation_WAN-Context-Windows.api.json",
        ),
        ("scail2_video_replacement", "SCAIL-2_Replacement_audio.api.json"),
        (
            "scail2_face_swap_v2",
            "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
        ),
    ],
)
def test_scail2_task_types_resolve_to_api_workflows(task_type, filename):
    assert resolve_workflow_filename(task_type) == filename


def test_face_swap_versions_keep_distinct_workflows_and_shared_node_contract():
    assert resolve_workflow_filename("face_swap") == "face_swap.json"
    assert resolve_workflow_filename("face_swap_v2") == "face_swap_v2.json"

    mappings = validate_workflow_directory("workers/comfy_agent/workflows")
    assert mappings["face_swap"] == {"face_image": "2", "body_image": "3"}
    assert mappings["face_swap_v2"] == {"face_image": "2", "body_image": "3"}


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
