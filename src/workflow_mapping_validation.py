import json
import os
from pathlib import Path
from typing import Any

from src.domain_config.task_type_registry import (
    get_task_type_entry,
    workflow_filename_facts,
)

WORKFLOW_FILENAME_OVERRIDES_ENV = "TASK_TYPE_WORKFLOW_OVERRIDES"


TASK_TYPE_WORKFLOW_FILENAMES = workflow_filename_facts()


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
    normalized_task_type = str(task_type or "").strip()
    registered_filename = TASK_TYPE_WORKFLOW_FILENAMES.get(normalized_task_type)
    if registered_filename is None:
        if get_task_type_entry(normalized_task_type) is not None:
            raise WorkflowMappingValidationError(
                f"registered task type has no workflow: {normalized_task_type}"
            )
        raise WorkflowMappingValidationError(
            f"unknown task type has no workflow contract: {normalized_task_type}"
        )
    overrides = _load_workflow_filename_overrides()
    if normalized_task_type in overrides:
        return overrides[normalized_task_type]
    return registered_filename


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
