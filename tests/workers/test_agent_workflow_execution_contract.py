import sys
from pathlib import Path

from PIL import Image
import pytest

WORKER_DIR = Path(__file__).resolve().parents[2] / "workers" / "comfy_agent"
sys.path.insert(0, str(WORKER_DIR))

from agent_workflow_execution import validate_task_execution_contract  # noqa: E402


def test_h3_flf2v_worker_rejects_mismatched_frame_aspects(tmp_path, monkeypatch):
    Image.new("RGB", (600, 900)).save(tmp_path / "first.png")
    Image.new("RGB", (900, 600)).save(tmp_path / "last.png")
    monkeypatch.setenv("COMFY_INPUT_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="aspect ratios must match"):
        validate_task_execution_contract(
            task_type="minimax_h3_flf2v",
            params={"image": "first.png", "image2": "last.png"},
        )


def test_h3_flf2v_worker_accepts_matching_frame_aspects(tmp_path, monkeypatch):
    Image.new("RGB", (600, 900)).save(tmp_path / "first.png")
    Image.new("RGB", (602, 900)).save(tmp_path / "last.png")
    monkeypatch.setenv("COMFY_INPUT_DIR", str(tmp_path))

    validate_task_execution_contract(
        task_type="minimax_h3_flf2v",
        params={"image": "first.png", "image2": "last.png"},
    )
