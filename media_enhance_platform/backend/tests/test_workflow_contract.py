import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from worker_contract.workflow import (  # noqa: E402
    WorkflowContractError,
    build_workflow,
    validate_catalog,
)


def test_workflow_catalog_has_required_nodes() -> None:
    assert validate_catalog() == []


def test_workflow_builder_injects_source_and_interpolation_multiplier() -> None:
    workflow = build_workflow("frame_interpolation", "input.mp4", 4)
    assert workflow["1"]["inputs"]["video"] == "input.mp4"
    assert workflow["2"]["inputs"]["multiplier"] == 4
    assert workflow["3"]["inputs"]["frame_rate"] == 120


def test_workflow_builder_rejects_unsupported_preset() -> None:
    try:
        build_workflow("video_upscale", "input.mp4", 4)
    except WorkflowContractError as exc:
        assert "multiplier" in str(exc)
    else:
        raise AssertionError("unsupported multiplier was accepted")


def test_upscale_builder_uses_source_dimensions_for_target_resolution() -> None:
    workflow = build_workflow(
        "image_upscale",
        "input.png",
        4,
        source_width=800,
        source_height=1200,
    )
    assert workflow["4"]["inputs"]["resolution"] == 4800
