"""Shared media preparation for the SCAIL-2 video face-swap pipeline."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from config import MINIO_BUCKET
from src.constants import MODE_FACE_SWAP_V2, MODE_SCAIL2_FACE_SWAP_V2
from src.core.billing_core import refund_credits
from src.core.task_core_finalization import build_task_refund_idempotency_key
from src.services.task_service_types import BotTaskRuntimeState
from src.services.storage import storage
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)

logger = logging.getLogger(__name__)
BOT_SCAIL2_FACE_SWAP_CONTINUATION_KEY = "_scail2_face_swap_continuation"


def build_scail2_first_frame_object_key(
    internal_user_id: int,
    registry_task_id: str,
) -> str:
    return (
        f"{int(internal_user_id)}/pipeline_inputs/"
        f"{registry_task_id}_scail2_face_swap_first_frame.png"
    )


def build_bot_scail2_stage2_task_id(registry_task_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"allbot:bot-scail2-face-swap:{registry_task_id}:video",
        )
    )


def extract_first_frame(video_path: Path, output_path: Path) -> None:
    result = subprocess.run(
        [
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if (
        result.returncode != 0
        or not output_path.exists()
        or output_path.stat().st_size <= 0
    ):
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Failed to extract SCAIL-2 driving first frame: {detail}")


def _normalize_storage_object_key(path: str, bucket_name: str) -> str:
    prefix = f"{bucket_name}/"
    return path[len(prefix) :] if path.startswith(prefix) else path


async def prepare_scail2_face_swap_first_frame(
    *,
    internal_user_id: int,
    registry_task_id: str,
    motion_video_path: str,
    storage_service=storage,
    bucket_name: str = MINIO_BUCKET,
    extract_first_frame_func: Callable[[Path, Path], None] = extract_first_frame,
) -> str:
    object_key = build_scail2_first_frame_object_key(
        internal_user_id,
        registry_task_id,
    )
    with tempfile.TemporaryDirectory(prefix="allbot-scail2-faceswap-") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = Path(motion_video_path)
        if not source_path.exists():
            source_path = temp_path / "motion-video"
            await asyncio.to_thread(
                storage_service.download_file,
                bucket_name,
                _normalize_storage_object_key(motion_video_path, bucket_name),
                str(source_path),
            )

        first_frame_path = temp_path / "first-frame.png"
        await asyncio.to_thread(
            extract_first_frame_func,
            source_path,
            first_frame_path,
        )
        if not first_frame_path.exists() or first_frame_path.stat().st_size <= 0:
            raise RuntimeError("SCAIL-2 first-frame extraction produced no image")

        uploaded = await asyncio.to_thread(
            storage_service.upload_file,
            str(first_frame_path),
            object_key,
            bucket_name,
        )
        if not uploaded:
            raise RuntimeError("Failed to upload SCAIL-2 first-frame pipeline input")
    return object_key


async def cleanup_scail2_face_swap_first_frame(
    object_key: str | None,
    *,
    storage_service=storage,
    bucket_name: str = MINIO_BUCKET,
) -> bool:
    if not object_key:
        return False
    client = getattr(storage_service, "client", None)
    if client is None:
        return False
    try:
        await asyncio.to_thread(
            client.remove_object,
            bucket_name,
            _normalize_storage_object_key(object_key, bucket_name),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to clean SCAIL-2 pipeline input %s: %s", object_key, exc)
        return False


async def process_bot_scail2_face_swap_pipeline(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    internal_user_id: int,
    username: str | None,
    reference_image_path: str,
    motion_video_path: str,
    prompt: str,
    duration: int,
    message_id: int | None,
    cleanup: bool,
    source_post_id: int | None,
    normal_priority: int,
    cost: int,
    prepare_first_frame_func=prepare_scail2_face_swap_first_frame,
    process_generation_task_func=None,
    download_output_file_func=download_output_file_to_fsm_temp,
    process_scail2_stage_func: Callable[..., Awaitable[Any]],
    runtime_state: BotTaskRuntimeState | Any | None = None,
    cleanup_first_frame_func=cleanup_scail2_face_swap_first_frame,
    refund_root_func=None,
) -> Any:
    if process_generation_task_func is None:
        raise RuntimeError("SCAIL-2 pipeline generation executor is not configured")
    refund_root_func = refund_root_func or _refund_bot_pipeline_root
    pipeline_id = str(uuid.uuid4())
    first_frame = await prepare_first_frame_func(
        internal_user_id=internal_user_id,
        registry_task_id=pipeline_id,
        motion_video_path=motion_video_path,
    )
    stage1_runtime = runtime_state or BotTaskRuntimeState(actual_cost=cost)
    try:
        _media_bytes, swapped_output = await process_generation_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt="face swap",
            images=[first_frame, reference_image_path, motion_video_path],
            task_type=MODE_FACE_SWAP_V2,
            cleanup=False,
            send_result=False,
            record_history=False,
            allow_contribute=False,
            cost_override=cost,
            base_priority=100,
            allow_cancel=True,
            user_cancel_allowed=True,
            runtime_state=stage1_runtime,
            result_meta={
                BOT_SCAIL2_FACE_SWAP_CONTINUATION_KEY: {
                    "version": 1,
                    "duration": duration,
                    "prompt": prompt,
                    "normal_priority": normal_priority,
                    "cost": cost,
                    "reference_input_index": 1,
                    "motion_video_input_index": 2,
                }
            },
        )
    finally:
        await cleanup_first_frame_func(first_frame)
    if not swapped_output:
        return None

    suffix = Path(str(swapped_output)).suffix or ".png"
    swapped_reference = await download_output_file_func(
        output_file=str(swapped_output),
        suffix=suffix,
        name_hint="scail2_face_swap_reference",
    )
    try:
        root_registry_task_id = getattr(stage1_runtime, "registry_task_id", None)
        result = await process_scail2_stage_func(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            task_type=MODE_SCAIL2_FACE_SWAP_V2,
            reference_image_path=swapped_reference,
            motion_video_path=motion_video_path,
            prompt=prompt,
            duration=duration,
            message_id=message_id,
            cleanup=cleanup,
            source_post_id=source_post_id,
            reference_preprocessed=True,
            history_reference_image_path=reference_image_path,
            deduct_quota=False,
            cost_override=0,
            base_priority=normal_priority,
            allow_cancel=False,
            user_cancel_allowed=False,
            task_id_override=(
                build_bot_scail2_stage2_task_id(root_registry_task_id)
                if root_registry_task_id
                else None
            ),
        )
    except Exception:
        await refund_root_func(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            registry_task_id=getattr(stage1_runtime, "registry_task_id", None),
        )
        raise

    output_path = result[1] if isinstance(result, tuple) and len(result) > 1 else None
    if not output_path:
        await refund_root_func(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            registry_task_id=getattr(stage1_runtime, "registry_task_id", None),
        )
    return result


async def _refund_bot_pipeline_root(
    *,
    internal_user_id: int,
    username: str | None,
    cost: int,
    registry_task_id: str | None,
) -> None:
    if not registry_task_id:
        return
    await refund_credits(
        internal_user_id,
        cost,
        task_type="refund_scail2_face_swap_pipeline",
        username=username,
        idempotency_key=build_task_refund_idempotency_key(
            refund_task_type="refund_scail2_face_swap_pipeline",
            registry_task_id=registry_task_id,
        ),
    )
