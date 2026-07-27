import asyncio
import io
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from agent_result_assets import (
    LAST_FRAME_EXTRA_OUTPUT_TASK_TYPES,
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


def _build_fallback_last_frame_object_name(primary_object_name: str) -> str:
    stem = str(primary_object_name or "").rsplit(".", 1)[0]
    if "_video_" in stem:
        prefix, suffix = stem.rsplit("_video_", 1)
        stem = f"{prefix}_last_frame_{suffix}"
    elif stem.endswith("_video"):
        stem = f"{stem[:-6]}_last_frame"
    else:
        stem = f"{stem}_last_frame"
    return f"{stem}.png"


def _probe_video_duration_seconds(input_path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return None


def _run_last_frame_ffmpeg(input_path: Path, output_path: Path) -> bool:
    duration = _probe_video_duration_seconds(input_path)
    commands: list[list[str]] = []
    if duration and duration > 0:
        commands.append(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{max(duration - 0.08, 0):.3f}",
                "-i",
                str(input_path),
                "-frames:v",
                "1",
                str(output_path),
            ]
        )
    commands.append(
        [
            "ffmpeg",
            "-y",
            "-sseof",
            "-0.5",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
    )

    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True)
        if (
            result.returncode == 0
            and output_path.exists()
            and output_path.stat().st_size
        ):
            return True
    return False


def _extract_last_frame_from_video_bytes(video_bytes: bytes, logger) -> bytes | None:
    if not video_bytes:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mp4"
            output_path = Path(tmpdir) / "last_frame.png"
            input_path.write_bytes(video_bytes)
            if not _run_last_frame_ffmpeg(input_path, output_path):
                logger.warning("Failed to extract fallback last frame with ffmpeg")
                return None
            return output_path.read_bytes()
    except Exception as exc:
        logger.warning("Failed to extract fallback last frame: %s", exc)
        return None


def _character_view_assets(
    history: dict[str, Any], prompt_id: str
) -> list[dict[str, Any]]:
    prompt_history = history.get(prompt_id) or {}
    outputs = prompt_history.get("outputs") or {}
    matched: dict[int, dict[str, Any]] = {}
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for asset in node_output.get("images", []) or []:
            filename = str(asset.get("filename") or "")
            marker = "character_reference_view_"
            if marker not in filename:
                continue
            try:
                index = int(filename.split(marker, 1)[1][:2])
            except (TypeError, ValueError):
                continue
            if index in matched:
                raise RuntimeError(f"duplicate character reference view {index:02d}")
            matched[index] = asset
    if set(matched) != set(range(1, 7)):
        missing = sorted(set(range(1, 7)) - set(matched))
        raise RuntimeError(f"character reference workflow missing views: {missing}")
    return [matched[index] for index in range(1, 7)]


def _compose_character_sheet(images: list[bytes]) -> bytes:
    if len(images) != 6:
        raise RuntimeError("character reference sheet requires exactly six views")
    canvas = Image.new("RGB", (1536, 896), "black")
    for index, payload in enumerate(images):
        try:
            with Image.open(io.BytesIO(payload)) as source:
                tile = ImageOps.fit(
                    source.convert("RGB"), (512, 448), method=Image.Resampling.LANCZOS
                )
        except Exception as exc:
            raise RuntimeError(
                f"corrupt character reference view {index + 1:02d}"
            ) from exc
        canvas.paste(tile, ((index % 3) * 512, (index // 3) * 448))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


async def _materialize_character_reference(
    *, comfy_client, execution, history
) -> MaterializedTaskOutputs:
    assets = _character_view_assets(history, execution.prompt_id)
    image_bytes = []
    for asset in assets:
        image_bytes.append(
            await comfy_client.get_view(
                asset["filename"],
                asset.get("subfolder", ""),
                type=asset.get("type", "output"),
            )
        )
    result_name = f"{execution.task_id}_character_reference.png"
    execution.task_result = result_name
    execution.task_result_priority = 0
    return MaterializedTaskOutputs(
        primary=MaterializedPrimaryResult(
            object_name=result_name,
            file_name=result_name,
            subfolder="",
            view_type="output",
            content_type="image/png",
            file_data=await asyncio.to_thread(_compose_character_sheet, image_bytes),
        ),
        extra_outputs={},
    )


async def materialize_task_outputs(
    *,
    comfy_client,
    execution,
    task_type: str,
    logger,
) -> MaterializedTaskOutputs:
    history = await comfy_client.get_history(execution.prompt_id)
    if task_type == "character_reference_build":
        return await _materialize_character_reference(
            comfy_client=comfy_client,
            execution=execution,
            history=history,
        )
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

    if (
        task_type in LAST_FRAME_EXTRA_OUTPUT_TASK_TYPES
        and "last_frame" not in materialized_extra_outputs
        and primary.content_type == "video/mp4"
    ):
        fallback_last_frame = await asyncio.to_thread(
            _extract_last_frame_from_video_bytes,
            primary.file_data,
            logger,
        )
        if fallback_last_frame:
            materialized_extra_outputs["last_frame"] = MaterializedExtraOutput(
                object_name=_build_fallback_last_frame_object_name(primary.object_name),
                media_type="image",
                content_type="image/png",
                file_data=fallback_last_frame,
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
