from dataclasses import dataclass
from typing import Any

from agent_result_assets import (
    resolve_comfy_view_type,
    resolve_history_extra_output_assets,
    resolve_history_result_asset,
    result_asset_priority,
)


@dataclass(frozen=True)
class MaterializedPrimaryResult:
    object_name: str
    file_name: str
    subfolder: str
    view_type: str
    content_type: str
    file_data: bytes


@dataclass(frozen=True)
class MaterializedExtraOutput:
    object_name: str
    media_type: str
    content_type: str
    file_data: bytes


@dataclass(frozen=True)
class MaterializedTaskOutputs:
    primary: MaterializedPrimaryResult
    extra_outputs: dict[str, MaterializedExtraOutput]


def _resolve_content_type(file_name: str) -> str:
    lower_name = file_name.lower()
    if lower_name.endswith(".mp4"):
        return "video/mp4"
    if lower_name.endswith(".gif"):
        return "image/gif"
    if lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
        return "image/jpeg"
    return "image/png"


async def materialize_task_outputs(
    *,
    comfy_client,
    execution,
    task_type: str,
    logger,
) -> MaterializedTaskOutputs:
    history = await comfy_client.get_history(execution.prompt_id)
    history_result = resolve_history_result_asset(
        history,
        prompt_id=execution.prompt_id,
        task_id=execution.task_id,
        task_type=task_type,
    )
    if not history_result:
        raise RuntimeError("Could not retrieve original filename from ComfyUI history")

    execution.task_result = history_result["safe_name"]
    execution.task_result_priority = result_asset_priority(
        history_result,
        task_type=task_type,
    )

    extra_output_assets = resolve_history_extra_output_assets(
        history,
        prompt_id=execution.prompt_id,
        task_id=execution.task_id,
        task_type=task_type,
    )

    original_filename = history_result["filename"]
    original_subfolder = history_result["subfolder"]
    view_type = resolve_comfy_view_type(history_result)
    logger.info(
        "Fetching result %s from ComfyUI API (subfolder: '%s', type: '%s')",
        original_filename,
        original_subfolder,
        view_type,
    )
    primary_bytes = await comfy_client.get_view(
        original_filename,
        original_subfolder,
        type=view_type,
    )
    primary = MaterializedPrimaryResult(
        object_name=execution.task_result,
        file_name=original_filename,
        subfolder=original_subfolder,
        view_type=view_type,
        content_type=_resolve_content_type(original_filename),
        file_data=primary_bytes,
    )

    materialized_extra_outputs: dict[str, MaterializedExtraOutput] = {}
    for name, extra_output in list(extra_output_assets.items()):
        extra_filename = extra_output.get("filename")
        extra_subfolder = extra_output.get("subfolder")
        if not extra_filename or extra_subfolder is None:
            continue
        extra_view_type = extra_output.get("type", "output")
        extra_file_data = await comfy_client.get_view(
            extra_filename,
            extra_subfolder,
            type=extra_view_type,
        )
        materialized_extra_outputs[name] = MaterializedExtraOutput(
            object_name=extra_output["path"],
            media_type=extra_output.get("media_type", "image"),
            content_type=_resolve_content_type(extra_filename),
            file_data=extra_file_data,
        )

    return MaterializedTaskOutputs(
        primary=primary,
        extra_outputs=materialized_extra_outputs,
    )


async def resolve_execution_result_from_history(
    *,
    comfy_client,
    execution,
    task_type: str,
    logger,
) -> dict[str, Any]:
    if execution.task_result:
        return {}

    logger.info(
        "Task result not set via WS, checking history for prompt %s",
        execution.prompt_id,
    )
    try:
        history = await comfy_client.get_history(execution.prompt_id)
        history_result = resolve_history_result_asset(
            history,
            prompt_id=execution.prompt_id,
            task_id=execution.task_id,
            task_type=task_type,
        )
        if history_result:
            execution.task_result = history_result["safe_name"]
            execution.task_result_priority = result_asset_priority(
                history_result,
                task_type=task_type,
            )
        return resolve_history_extra_output_assets(
            history,
            prompt_id=execution.prompt_id,
            task_id=execution.task_id,
            task_type=task_type,
        )
    except Exception as exc:
        logger.warning("Failed to fetch history: %s", exc)
        return {}
