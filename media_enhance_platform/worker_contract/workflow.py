from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "workflows"


class WorkflowContractError(ValueError):
    pass


def load_catalog() -> dict:
    return json.loads((WORKFLOW_DIR / "catalog.json").read_text())


def build_workflow(
    task_type: str,
    source_filename: str,
    multiplier: int,
    *,
    source_width: int | None = None,
    source_height: int | None = None,
) -> dict:
    catalog = load_catalog()["workflows"]
    if task_type not in catalog:
        raise WorkflowContractError("unsupported task type")
    contract = catalog[task_type]
    if multiplier not in contract["multipliers"]:
        raise WorkflowContractError("unsupported multiplier")
    workflow = json.loads((WORKFLOW_DIR / contract["file"]).read_text())
    source_node = workflow.get(contract["source_node"])
    if not source_node:
        raise WorkflowContractError("source node missing")
    source_node["inputs"][contract["source_input"]] = source_filename
    if task_type in {"image_upscale", "video_upscale"}:
        if not source_width or not source_height:
            raise WorkflowContractError("source dimensions are required")
        resolution_node = workflow[contract["resolution_node"]]
        resolution_node["inputs"][contract["resolution_input"]] = (
            max(source_width, source_height) * multiplier
        )
    elif task_type == "frame_interpolation":
        workflow[contract["multiplier_node"]]["inputs"][
            contract["multiplier_input"]
        ] = multiplier
        workflow[contract["output_node"]]["inputs"]["frame_rate"] = 30 * multiplier
    return copy.deepcopy(workflow)


def validate_catalog() -> list[str]:
    errors: list[str] = []
    catalog = load_catalog()["workflows"]
    required_classes = {
        "image_upscale": {"LoadImage", "SeedVR2VideoUpscaler", "SaveImage"},
        "video_upscale": {"VHS_LoadVideo", "SeedVR2VideoUpscaler", "VHS_VideoCombine"},
        "frame_interpolation": {"VHS_LoadVideo", "FL_RIFE", "VHS_VideoCombine"},
    }
    for task_type, contract in catalog.items():
        path = WORKFLOW_DIR / contract["file"]
        if not path.exists():
            errors.append(f"{task_type}: workflow missing")
            continue
        workflow = json.loads(path.read_text())
        classes = {node.get("class_type") for node in workflow.values()}
        missing = required_classes[task_type] - classes
        if missing:
            errors.append(f"{task_type}: missing classes {sorted(missing)}")
        for key in ("source_node", "output_node"):
            if contract[key] not in workflow:
                errors.append(f"{task_type}: {key} missing")
    return errors
