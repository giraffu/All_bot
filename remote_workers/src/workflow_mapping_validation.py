import json
import os
from pathlib import Path
from typing import Any


WORKFLOW_FILENAME_OVERRIDES_ENV = "TASK_TYPE_WORKFLOW_OVERRIDES"


TASK_TYPE_WORKFLOW_FILENAMES = {
    "img2img": "Qwen-Rapid-AIO.json",
    "face_swap": "face_swap.json",
    "video_insert": "Wan22AioV82.json",
    "video_edit": "Wan22AioV82.json",
    "image_to_video": "Wan22AioV82.json",
    "face_video": "face_video.json",
    "t2i-pornmaster-turbo": (
        "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
    ),
    "i2i_pro": "i2i_pro.json",
    "i2i_draw": "I2I_draw.json",
    "img2img_lora": "Qwen-Rapid-AIO.json",
    "ltx_video": "LTX 2.3 I2V 6.1.json",
    "ltx_video_flf2v": "LTX 2.3 FLF2V 6.1.json",
    "ltx_video_v2v_audio": "LTX 2.3 V2V Audio 6.1.json",
    "wan22_video_v2": "Wan22AioV82.json",
    "scail2_action_transfer": "SCAIL-2_Animation_multi-char_audio.api.json",
    "scail2_video_replacement": "SCAIL-2_Replacement_audio.api.json",
    "scail2_face_swap_v2": "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
    "pornmaster_flux2_single_edit": (
        "PornMaster_F2K_9B_Turbo_Single-image-editing_Automatic_V1_2026_05_27.api.json"
    ),
    "pornmaster_flux2_multi_edit": (
        "PornMaster_F2K_9B_Turbo_Multiple-images-editing_Automatic_V1_2026_05_27.api.json"
    ),
}


class WorkflowMappingValidationError(ValueError):
    pass


def _load_workflow_filename_overrides() -> dict[str, str]:
    raw_overrides = os.getenv(WORKFLOW_FILENAME_OVERRIDES_ENV, "").strip()
    if not raw_overrides:
        return {}

    try:
        parsed = json.loads(raw_overrides)
    except json.JSONDecodeError as exc:
        raise WorkflowMappingValidationError(
            f"{WORKFLOW_FILENAME_OVERRIDES_ENV} must be a JSON object"
        ) from exc

    if not isinstance(parsed, dict):
        raise WorkflowMappingValidationError(
            f"{WORKFLOW_FILENAME_OVERRIDES_ENV} must be a JSON object"
        )

    overrides: dict[str, str] = {}
    for task_type, filename in parsed.items():
        if not isinstance(task_type, str) or not task_type.strip():
            raise WorkflowMappingValidationError(
                f"{WORKFLOW_FILENAME_OVERRIDES_ENV} keys must be non-empty strings"
            )
        if not isinstance(filename, str) or not filename.strip():
            raise WorkflowMappingValidationError(
                f"{WORKFLOW_FILENAME_OVERRIDES_ENV}.{task_type} must be a non-empty string"
            )
        workflow_path = Path(filename.strip())
        if workflow_path.is_absolute() or ".." in workflow_path.parts:
            raise WorkflowMappingValidationError(
                f"{WORKFLOW_FILENAME_OVERRIDES_ENV}.{task_type} must stay under the workflow directory"
            )
        overrides[task_type.strip()] = filename.strip()

    return overrides


def resolve_workflow_filename(task_type: str) -> str:
    overrides = _load_workflow_filename_overrides()
    if task_type in overrides:
        return overrides[task_type]
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
