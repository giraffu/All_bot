import asyncio
import json
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent_result_assets import resolve_history_result_asset
from comfy_client import ComfyClient


def _safe_stem(value: str, *, fallback: str = "scail2_face_swap_v10") -> str:
    text = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    text = text.strip("_")
    return text[:96] or fallback


def extract_first_frame(video_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Failed to extract first frame from driving video: {detail}")


def _load_workflow_by_filename(workflows_dir: Path, filename: str, patcher) -> dict[str, Any]:
    workflow_path = workflows_dir / filename
    if not workflow_path.exists():
        raise RuntimeError(f"Face-swap v10 helper workflow not found: {workflow_path}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    return patcher.strip_meta(workflow)


def _set_save_image_prefix(workflow: dict[str, Any], prefix: str) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "SaveImage":
            continue
        node.setdefault("inputs", {})["filename_prefix"] = prefix
        return


def _resolve_prepared_input_path(
    *,
    input_dir: Path,
    filename: str,
    downloaded_input_paths: list[str],
) -> Path:
    direct_path = input_dir / filename
    if direct_path.exists():
        return direct_path
    for candidate in downloaded_input_paths:
        candidate_path = Path(candidate)
        if candidate_path.name == filename and candidate_path.exists():
            return candidate_path
    return direct_path


async def _wait_for_image_result(
    *,
    comfy_client: ComfyClient,
    prompt_id: str,
    task_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        history = await comfy_client.get_history(prompt_id)
        result = resolve_history_result_asset(
            history,
            prompt_id=prompt_id,
            task_id=task_id,
            task_type="face_swap",
        )
        if result:
            return result
        if loop.time() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for first-frame face swap result ({prompt_id})"
            )
        await asyncio.sleep(poll_interval_seconds)


async def prepare_scail2_face_swap_v10_reference(
    *,
    task_id: str,
    params: dict[str, Any],
    downloaded_input_paths: list[str],
    comfy_input_dir: str,
    workflows_dir: str,
    patcher,
    primary_comfy_client: ComfyClient,
    face_swap_comfy_api_url: str,
    face_swap_workflow_filename: str,
    client_id: str,
    logger,
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 2.0,
    comfy_client_factory: Callable[[str], ComfyClient] = ComfyClient,
    extract_first_frame_func: Callable[[Path, Path], None] = extract_first_frame,
) -> str:
    reference_name = str(params.get("image") or "").strip()
    video_name = str(params.get("video") or "").strip()
    if not reference_name or not video_name:
        raise RuntimeError("SCAIL-2 face swap v10 requires both reference image and video")

    input_dir = Path(comfy_input_dir)
    reference_path = _resolve_prepared_input_path(
        input_dir=input_dir,
        filename=reference_name,
        downloaded_input_paths=downloaded_input_paths,
    )
    video_path = _resolve_prepared_input_path(
        input_dir=input_dir,
        filename=video_name,
        downloaded_input_paths=downloaded_input_paths,
    )
    if not reference_path.exists():
        raise RuntimeError(f"Prepared reference image not found: {reference_path}")
    if not video_path.exists():
        raise RuntimeError(f"Prepared driving video not found: {video_path}")

    safe_task_stem = _safe_stem(task_id)
    first_frame_name = f"{safe_task_stem}_v10_driving_first_frame.png"
    first_frame_path = input_dir / first_frame_name
    extract_first_frame_func(video_path, first_frame_path)
    downloaded_input_paths.append(str(first_frame_path))

    aux_face_name = f"{safe_task_stem}_v10_face_reference.png"
    aux_first_frame_name = f"{safe_task_stem}_v10_body_first_frame.png"
    aux_task_id = f"{safe_task_stem}_v10_firstframe_faceswap"
    seed = (
        int(params.get("seed") or 0)
        or abs(hash((task_id, reference_name, video_name))) % 1125899906842624
    )

    aux_client = comfy_client_factory(face_swap_comfy_api_url)
    try:
        await aux_client.upload_image(reference_path.read_bytes(), aux_face_name)
        await aux_client.upload_image(first_frame_path.read_bytes(), aux_first_frame_name)

        workflow = _load_workflow_by_filename(
            Path(workflows_dir),
            face_swap_workflow_filename,
            patcher,
        )
        patched = patcher.patch_workflow(
            "face_swap",
            workflow,
            {
                "face_image": aux_face_name,
                "body_image": aux_first_frame_name,
                "seed": seed,
            },
        )
        _set_save_image_prefix(patched, f"{aux_task_id}_image")

        logger.info(
            "Submitting SCAIL-2 face swap v10 first-frame image swap via %s",
            face_swap_comfy_api_url,
        )
        prompt_id = await aux_client.queue_prompt(patched, client_id)
        result = await _wait_for_image_result(
            comfy_client=aux_client,
            prompt_id=prompt_id,
            task_id=aux_task_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        swapped_bytes = await aux_client.get_view(
            result["filename"],
            result["subfolder"],
            type=result.get("type") or "output",
        )
    finally:
        await aux_client.close()

    swapped_name = f"{safe_task_stem}_v10_swapped_first_frame.png"
    swapped_path = input_dir / swapped_name
    swapped_path.write_bytes(swapped_bytes)
    downloaded_input_paths.append(str(swapped_path))

    await primary_comfy_client.upload_image(swapped_bytes, swapped_name)
    params["image"] = swapped_name
    logger.info("SCAIL-2 face swap v10 reference image prepared: %s", swapped_name)
    return swapped_name
