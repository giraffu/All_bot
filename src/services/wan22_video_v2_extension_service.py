import asyncio
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select

from src.core.media_paths import resolve_storage_object
from src.core import user_core
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.storage import storage
from src.services.task_service_generation_wan22 import (
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    normalize_wan22_video_v2_chain_task_ids,
    normalize_wan22_video_v2_resolution_preset,
)


class Wan22VideoV2ExtensionError(Exception):
    """Raised when WAN2.2 extension or stitching prerequisites are not met."""


async def resolve_internal_user_id_from_telegram(
    telegram_user_id: int,
    username: str | None,
) -> int:
    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        telegram_user_id,
        username,
    )
    return internal_user.id


async def load_owned_wan22_history(
    *,
    task_id: str,
    telegram_user_id: int,
    username: str | None,
) -> History:
    internal_user_id = await resolve_internal_user_id_from_telegram(
        telegram_user_id,
        username,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == internal_user_id,
            )
        )
        history = result.scalar_one_or_none()
    if history is None:
        raise Wan22VideoV2ExtensionError("未找到对应的视频记录，或该记录不属于您。")
    if history.type != "wan22_video_v2":
        raise Wan22VideoV2ExtensionError("当前仅支持图生视频 v2 的扩展生成。")
    return history


def resolve_last_frame_output_file(history: History) -> str:
    extra_outputs = history.extra_outputs or {}
    last_frame = extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
    output_file = last_frame.get("path") if isinstance(last_frame, dict) else None
    if not output_file:
        raise Wan22VideoV2ExtensionError("这条记录没有可用的尾帧图片，请先重新生成带尾帧提取的视频。")
    return str(output_file)


def resolve_extension_resolution_preset(result_meta: dict | None) -> str:
    if not isinstance(result_meta, dict):
        return WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    return normalize_wan22_video_v2_resolution_preset(
        result_meta.get("wan22_resolution_preset")
    )


def resolve_extension_chain_task_ids(result_meta: dict | None) -> list[str]:
    if not isinstance(result_meta, dict):
        return []
    return normalize_wan22_video_v2_chain_task_ids(
        result_meta.get("wan22_chain_task_ids")
    )


async def download_output_file_to_fsm_temp(
    *,
    output_file: str,
    suffix: str,
    name_hint: str,
) -> str:
    bucket_name, object_name = resolve_storage_object(output_file)
    temp_dir = Path(FSM_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_path = temp_dir / f"{uuid.uuid4()}_{name_hint}{suffix}"
    await asyncio.to_thread(
        storage.download_file,
        bucket_name,
        object_name,
        str(local_path),
    )
    return str(local_path)


async def download_last_frame_to_fsm_temp(
    *,
    history: History,
    name_hint: str = "wan22_video_v2_extension_start",
) -> str:
    output_file = resolve_last_frame_output_file(history)
    suffix = Path(output_file).suffix or ".png"
    return await download_output_file_to_fsm_temp(
        output_file=output_file,
        suffix=suffix,
        name_hint=name_hint,
    )


def resolve_history_input_files(history: History) -> list[str]:
    input_file = str(history.input_file or "").strip()
    if not input_file:
        return []
    return [part.strip() for part in input_file.split("|") if part.strip()]


async def download_history_input_file_to_fsm_temp(
    *,
    history: History,
    index: int,
    name_hint: str,
) -> str:
    input_files = resolve_history_input_files(history)
    try:
        output_file = input_files[index]
    except IndexError as exc:
        raise Wan22VideoV2ExtensionError("当前段落没有可复用的尾帧输入图。") from exc
    suffix = Path(output_file).suffix or ".png"
    return await download_output_file_to_fsm_temp(
        output_file=output_file,
        suffix=suffix,
        name_hint=name_hint,
    )


def build_full_chain_task_ids(
    *,
    chain_task_ids: list[str],
    current_task_id: str,
) -> list[str]:
    ordered: list[str] = []
    for task_id in [*chain_task_ids, current_task_id]:
        normalized = str(task_id or "").strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def _download_output_to_local_file(*, output_file: str, target_path: Path) -> None:
    bucket_name, object_name = resolve_storage_object(output_file)
    storage.download_file(bucket_name, object_name, str(target_path))


async def stitch_history_videos(histories: list[History]) -> bytes:
    if len(histories) < 2:
        raise Wan22VideoV2ExtensionError("至少需要两段视频才能执行拼接。")
    temp_dir = Path(tempfile.mkdtemp(prefix="wan22v2_stitch_"))
    try:
        local_inputs: list[Path] = []
        for index, history in enumerate(histories, start=1):
            if not history.output_file:
                raise Wan22VideoV2ExtensionError("存在缺少视频文件的历史记录，无法拼接。")
            local_input = temp_dir / f"segment_{index}.mp4"
            await asyncio.to_thread(
                _download_output_to_local_file,
                output_file=str(history.output_file),
                target_path=local_input,
            )
            local_inputs.append(local_input)

        concat_list_path = temp_dir / "concat.txt"
        concat_list_path.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in local_inputs),
            encoding="utf-8",
        )
        output_path = temp_dir / "stitched.mp4"
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
        await asyncio.to_thread(
            subprocess.run,
            ffmpeg_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return output_path.read_bytes()
    except FileNotFoundError as exc:
        raise Wan22VideoV2ExtensionError("服务器未安装 ffmpeg，暂时无法完成视频拼接。") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
        raise Wan22VideoV2ExtensionError(
            f"视频拼接失败，请稍后重试。{stderr[:200]}".strip()
        ) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
