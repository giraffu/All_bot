import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select

from src.constants import MODE_LTX_VIDEO
from src.core.media_paths import resolve_storage_object
from src.core import user_core
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.storage import storage


class LtxVideoExtensionError(Exception):
    """Raised when an LTX video record cannot be reused for extension."""


async def resolve_internal_user_id_from_telegram(
    telegram_user_id: int,
    username: str | None,
) -> int:
    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        telegram_user_id,
        username,
    )
    return internal_user.id


async def load_owned_ltx_history(
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
        raise LtxVideoExtensionError("未找到对应的视频记录，或该记录不属于您。")
    if history.type != MODE_LTX_VIDEO:
        raise LtxVideoExtensionError("当前仅支持 LTX 高级图生视频记录的扩展生成。")
    return history


def resolve_ltx_last_frame_output_file(history: History) -> str:
    extra_outputs = history.extra_outputs or {}
    last_frame = extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
    output_file = last_frame.get("path") if isinstance(last_frame, dict) else None
    if not output_file:
        raise LtxVideoExtensionError("这条记录没有可用的尾帧图片，请先重新生成该段视频。")
    return str(output_file)


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


async def download_ltx_last_frame_to_fsm_temp(
    *,
    history: History,
    name_hint: str = "ltx_video_extension_start",
) -> str:
    output_file = resolve_ltx_last_frame_output_file(history)
    suffix = Path(output_file).suffix or ".png"
    return await download_output_file_to_fsm_temp(
        output_file=output_file,
        suffix=suffix,
        name_hint=name_hint,
    )
