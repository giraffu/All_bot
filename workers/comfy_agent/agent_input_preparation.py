import asyncio
from collections.abc import Awaitable, Callable
import glob
import json
import os
from pathlib import Path
import subprocess
from typing import Any

try:
    from agent_artifact_lifecycle import (
        artifact_ref_from_comfy_response,
        safe_artifact_component,
    )
except ImportError:  # pragma: no cover - package import in focused tests
    from .agent_artifact_lifecycle import (
        artifact_ref_from_comfy_response,
        safe_artifact_component,
    )


LTX25_UPSCALE_MAX_SOURCE_DURATION_SECONDS = 5.25
LTX25_UPSCALE_ENCODING_CUTOFF_SECONDS = 5.1


def _cleanup_partial_downloads(local_path: str) -> None:
    for path in [local_path, *glob.glob(f"{local_path}.*.part.minio")]:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue


def prepare_h3_reference_video_tail(param_key: str, local_path: str) -> str:
    """Normalize an internal H3 extension reference to its final five seconds."""
    if param_key != "reference_video":
        return local_path
    source = Path(local_path)
    output = source.with_name(f"{source.stem}__tail5s.mp4")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-sseof",
                "-5",
                "-i",
                str(source),
                "-t",
                "5",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-vf",
                "fps=24",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "32000",
                "-ac",
                "2",
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to trim H3 reference video: {exc}") from exc
    if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to trim H3 reference video: {detail or 'ffmpeg failed'}")
    return str(output)


def prepare_ltx25_video_upscale_input(param_key: str, local_path: str) -> str:
    """Create the fixed 5s/24fps/121-frame, Div32 source for 2x LTX-2.5."""
    if param_key != "video":
        return local_path
    source = Path(local_path)
    output = source.with_name(f"{source.stem}__ltx25_5s_24fps.mp4")
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type:format=duration",
                "-of",
                "json",
                str(source),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if probe.returncode != 0:
            raise RuntimeError(
                probe.stderr.decode("utf-8", errors="replace").strip()
                or "ffprobe failed"
            )
        probe_payload = json.loads(probe.stdout.decode("utf-8"))
        streams = probe_payload.get("streams", [])
        duration = float(probe_payload.get("format", {}).get("duration") or 0)
        if duration > LTX25_UPSCALE_MAX_SOURCE_DURATION_SECONDS:
            raise ValueError("source video exceeds the 5 second limit")
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
        ]
        if not has_audio:
            command.extend(
                ["-f", "lavfi", "-i", "anullsrc=r=32000:cl=stereo"]
            )
        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a:0" if has_audio else "1:a:0",
                "-vf",
                (
                    "fps=24,"
                    "scale='max(32,round(iw/32)*32)':'max(32,round(ih/32)*32)':"
                    "flags=lanczos,setsar=1,"
                    "tpad=stop_mode=clone:stop_duration=5.1"
                ),
                "-frames:v",
                "121",
                "-t",
                # Let the 121-frame cap define the exact 5.041667s video
                # duration. Using that same value as ffmpeg's time cutoff
                # drops the boundary frame on real 24fps H3 encodes.
                str(LTX25_UPSCALE_ENCODING_CUTOFF_SECONDS),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "32000",
                "-ac",
                "2",
                "-shortest",
                str(output),
            ]
        )
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to normalize LTX-2.5 upscale input: {exc}") from exc
    if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to normalize LTX-2.5 upscale input: {detail or 'ffmpeg failed'}"
        )
    return str(output)


async def _download_with_retries(
    *,
    download_input_func: Callable[[str, str], Any],
    img_filename: str,
    local_img_path: str,
    param_key: str,
    timeout_seconds: float | None,
    retry_attempts: int,
    retry_delay_seconds: float,
    logger,
) -> None:
    attempts = max(1, retry_attempts)
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            if timeout_seconds and timeout_seconds > 0:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        download_input_func, img_filename, local_img_path
                    ),
                    timeout=timeout_seconds,
                )
            else:
                await asyncio.to_thread(
                    download_input_func, img_filename, local_img_path
                )
            return
        except asyncio.TimeoutError as exc:
            last_error = exc
            _cleanup_partial_downloads(local_img_path)
            logger.warning(
                "Timed out downloading %s %s after %.1fs (attempt %s/%s)",
                param_key,
                img_filename,
                timeout_seconds,
                attempt,
                attempts,
            )
        except Exception as exc:
            last_error = exc
            _cleanup_partial_downloads(local_img_path)
            logger.warning(
                "Failed downloading %s %s on attempt %s/%s: %s",
                param_key,
                img_filename,
                attempt,
                attempts,
                exc,
            )

        if attempt < attempts and retry_delay_seconds > 0:
            await asyncio.sleep(retry_delay_seconds)

    raise RuntimeError(
        f"Failed to download {param_key} input '{img_filename}' after {attempts} attempts"
    ) from last_error


async def process_single_input_asset(
    *,
    params: dict[str, Any],
    downloaded_input_paths: list[str],
    uploaded_input_artifacts: list[Any] | None = None,
    comfy_filename_prefix: str = "",
    img_filename: str,
    param_key: str,
    comfy_input_dir: str,
    download_input_func: Callable[[str, str], Any],
    should_normalize_image_input_func: Callable[[str, str], bool],
    normalize_input_image_func: Callable[[str], str],
    prepare_input_file_func: Callable[[str, str], str] | None = None,
    upload_prepared_input_func: Callable[..., Awaitable[Any]],
    logger,
    download_timeout_seconds: float | None = None,
    download_retry_attempts: int = 1,
    download_retry_delay_seconds: float = 1.0,
) -> None:
    local_safe_filename = img_filename.replace("/", "_").replace("template:", "")
    local_img_path = os.path.join(comfy_input_dir, local_safe_filename)
    try:
        await _download_with_retries(
            download_input_func=download_input_func,
            img_filename=img_filename,
            local_img_path=local_img_path,
            param_key=param_key,
            timeout_seconds=download_timeout_seconds,
            retry_attempts=download_retry_attempts,
            retry_delay_seconds=download_retry_delay_seconds,
            logger=logger,
        )
        logger.info("Downloaded %s to %s", param_key, local_img_path)
        if local_img_path not in downloaded_input_paths:
            downloaded_input_paths.append(local_img_path)
        upload_path = local_img_path
        upload_name = local_safe_filename
        if prepare_input_file_func is not None:
            upload_path = await asyncio.to_thread(
                prepare_input_file_func,
                param_key,
                local_img_path,
            )
            upload_name = os.path.basename(upload_path)
            if upload_path not in downloaded_input_paths:
                downloaded_input_paths.append(upload_path)
        if should_normalize_image_input_func(param_key, img_filename):
            upload_path = await asyncio.to_thread(
                normalize_input_image_func,
                local_img_path,
            )
            upload_name = os.path.basename(upload_path)
            if upload_path not in downloaded_input_paths:
                downloaded_input_paths.append(upload_path)
            logger.info(
                "Normalized %s input for ComfyUI: %s -> %s",
                param_key,
                local_img_path,
                upload_path,
            )
        safe_prefix = safe_artifact_component(comfy_filename_prefix)
        comfy_upload_name = (
            f"{safe_prefix}_{upload_name}" if safe_prefix else upload_name
        )
        upload_response = await upload_prepared_input_func(
            upload_path=upload_path,
            upload_name=comfy_upload_name,
            source_name=img_filename,
        )
        if uploaded_input_artifacts is not None:
            uploaded_input_artifacts.append(
                artifact_ref_from_comfy_response(
                    upload_response,
                    fallback_name=comfy_upload_name,
                )
            )
        params[param_key] = str(
            upload_response.get("name")
            if isinstance(upload_response, dict) and upload_response.get("name")
            else comfy_upload_name
        )
        params[f"_prepared_{param_key}_path"] = upload_path
    except Exception as exc:
        logger.error("Failed to process %s %s: %s", param_key, img_filename, exc)
        raise RuntimeError(
            f"Failed to prepare {param_key} input '{img_filename}'"
        ) from exc


async def prepare_task_inputs(
    *,
    params: dict[str, Any],
    downloaded_input_paths: list[str],
    process_single_input_asset_func: Callable[..., Awaitable[None]],
) -> None:
    if (
        "images" in params
        and isinstance(params["images"], list)
        and len(params["images"]) > 0
    ):
        images_list = params["images"]
        tasks = []
        keys = ["image", "image2", "image3", "image4", "image5"]
        for i, img_filename in enumerate(images_list[:5]):
            tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=img_filename,
                    param_key=keys[i],
                )
            )
        if tasks:
            await asyncio.gather(*tasks)
    else:
        legacy_tasks = []
        if "image" in params and params["image"]:
            legacy_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params["image"],
                    param_key="image",
                )
            )
        if "image2" in params and params["image2"]:
            legacy_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params["image2"],
                    param_key="image2",
                )
            )
        if legacy_tasks:
            await asyncio.gather(*legacy_tasks)

    other_tasks = []
    for key in [
        "face_image",
        "body_image",
        "video",
        "end_image",
        "character_sheet",
        "background_image",
        "reference_video",
        "reference_audio",
    ]:
        if key in params and params[key]:
            other_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params[key],
                    param_key=key,
                )
            )
    character_sheets = params.get("character_sheets")
    character_sheet_keys = []
    if isinstance(character_sheets, list):
        for index, img_filename in enumerate(character_sheets[:4], start=1):
            if not img_filename:
                continue
            param_key = f"character_sheet_{index}"
            character_sheet_keys.append(param_key)
            other_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=img_filename,
                    param_key=param_key,
                )
            )
    if other_tasks:
        await asyncio.gather(*other_tasks)
    if character_sheet_keys:
        params["character_sheets"] = [params[key] for key in character_sheet_keys]
