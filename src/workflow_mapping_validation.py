import json
from pathlib import Path
from typing import Any


TASK_TYPE_WORKFLOW_FILENAMES = {
    "img2img": "Qwen-Rapid-AIO.json",
    "face_swap": "face_swap.json",
    "video_insert": "perfect_video_insert.json",
    "video_edit": "perfect_video_edit.json",
    "face_video": "face_video.json",
    "t2i-pornmaster-turbo": (
        "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
    ),
    "i2i_pro": "i2i_pro.json",
    "i2i_draw": "I2I_draw.json",
    "img2img_lora": "Qwen-Rapid-AIO.json",
    "ltx_video": "LTX 2.3 I2V.json",
}


class WorkflowMappingValidationError(ValueError):
    pass


def resolve_workflow_filename(task_type: str) -> str:
    return TASK_TYPE_WORKFLOW_FILENAMES.get(task_type, f"{task_type}.json")


def _load_json_file(file_path: Path) -> Any:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_workflow_mappings(workflows_dir: str) -> dict[str, Any]:
    mapping_path = Path(workflows_dir) / "mappings.json"
    if not mapping_path.exists():
        return {}
    mappings = _load_json_file(mapping_path)
    if not isinstance(mappings, dict):
        raise WorkflowMappingValidationError(
            f"Workflow mappings file must contain a JSON object: {mapping_path}"
        )
    return mappings


def validate_workflow_directory(workflows_dir: str) -> dict[str, Any]:
    mappings = load_workflow_mappings(workflows_dir)
    if not mappings:
        return mappings

    workflow_dir = Path(workflows_dir)
    errors: list[str] = []

    for task_type, mapping in mappings.items():
        if not isinstance(mapping, dict):
            errors.append(f"{task_type}: mapping must be a JSON object")
            continue

        workflow_filename = resolve_workflow_filename(task_type)
        workflow_path = workflow_dir / workflow_filename
        if not workflow_path.exists():
            errors.append(
                f"{task_type}: workflow file not found for mapping target {workflow_filename}"
            )
            continue

        workflow = _load_json_file(workflow_path)
        if not isinstance(workflow, dict):
            errors.append(f"{task_type}: workflow file must contain a JSON object")
            continue

        for param_key, node_id in mapping.items():
            if param_key.endswith("_input"):
                continue

            node = workflow.get(str(node_id))
            if not isinstance(node, dict):
                errors.append(
                    f"{task_type}.{param_key}: node {node_id} not found in {workflow_filename}"
                )
                continue

            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                errors.append(
                    f"{task_type}.{param_key}: node {node_id} has no inputs object"
                )
                continue

            input_name = mapping.get(f"{param_key}_input", "image")
            if input_name not in inputs:
                errors.append(
                    f"{task_type}.{param_key}: input {input_name!r} missing on node {node_id} in {workflow_filename}"
                )

    if errors:
        formatted_errors = "\n".join(f"- {message}" for message in errors)
        raise WorkflowMappingValidationError(
            f"Invalid workflow mappings under {workflow_dir}:\n{formatted_errors}"
        )

    return mappings
