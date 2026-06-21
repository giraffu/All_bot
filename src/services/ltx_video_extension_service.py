import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from src.constants import MODE_LTX_VIDEO
from src.core.media_paths import resolve_storage_object
from src.core import user_core
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.storage import storage
from src.services.wan22_video_v2_extension_service import (
    build_full_chain_task_ids,
    stitch_history_videos,
)


LTX_HISTORY_CONTEXT_KEY = "_ltx_context"
LTX_STITCH_RESULT_KEY = "ltx_chain_stitch"


class LtxVideoExtensionError(Exception):
    """Raised when an LTX video record cannot be reused for extension."""


class LtxVideoPersistenceError(LtxVideoExtensionError):
    """Raised when a stitched LTX result cannot be persisted."""


@dataclass(frozen=True)
class LtxVideoStitchedHistoryResult:
    video_bytes: bytes
    task_id: str
    task_type: str
    prompt: str
    output_file: str
    extra_outputs: dict[str, object]
    allow_contribute: bool
    segment_count: int
    history: History


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


async def load_owned_ltx_history_for_internal_user(
    *,
    task_id: str,
    internal_user_id: int,
) -> History:
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


def normalize_ltx_video_chain_task_ids(value) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    ordered: list[str] = []
    for item in raw_items:
        normalized = str(item or "").strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def build_ltx_full_chain_task_ids(
    *,
    chain_task_ids: list[str],
    current_task_id: str,
) -> list[str]:
    return build_full_chain_task_ids(
        chain_task_ids=chain_task_ids,
        current_task_id=current_task_id,
    )


def extract_ltx_history_context(extra_outputs: dict | None) -> dict[str, object]:
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(LTX_HISTORY_CONTEXT_KEY)
    if not isinstance(context, dict):
        return {}
    return dict(context)


def is_ltx_stitched_result(extra_outputs: dict | None) -> bool:
    if not isinstance(extra_outputs, dict):
        return False
    return isinstance(extra_outputs.get(LTX_STITCH_RESULT_KEY), dict)


def resolve_ltx_stitched_segment_count(extra_outputs: dict | None) -> int | None:
    if not isinstance(extra_outputs, dict):
        return None
    stitched_payload = extra_outputs.get(LTX_STITCH_RESULT_KEY)
    if not isinstance(stitched_payload, dict):
        return None
    raw_count = stitched_payload.get("segment_count")
    try:
        normalized_count = int(raw_count)
    except (TypeError, ValueError):
        normalized_count = 0
    if normalized_count > 0:
        return normalized_count
    chain_task_ids = normalize_ltx_video_chain_task_ids(
        stitched_payload.get("ltx_chain_task_ids")
    )
    return len(chain_task_ids) or None


def resolve_ltx_segment_index(extra_outputs: dict | None) -> int | None:
    if is_ltx_stitched_result(extra_outputs):
        return None
    context = extract_ltx_history_context(extra_outputs)
    if not context:
        return None
    chain_task_ids = normalize_ltx_video_chain_task_ids(
        context.get("ltx_chain_task_ids")
    )
    if chain_task_ids:
        return len(chain_task_ids) + 1
    prev_task_id = str(context.get("ltx_prev_task_id") or "").strip()
    if prev_task_id:
        return 2
    return 1


def build_ltx_history_context_from_metadata(metadata: dict | None) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    context: dict[str, object] = {}
    ltx_mode = str(metadata.get("ltx_mode") or "").strip()
    if ltx_mode:
        context["ltx_mode"] = ltx_mode
        context["ltx_use_end_frame"] = ltx_mode == "flf2v"
    if metadata.get("ltx_width") is not None:
        context["ltx_width"] = metadata.get("ltx_width")
    if metadata.get("ltx_height") is not None:
        context["ltx_height"] = metadata.get("ltx_height")
    if metadata.get("requested_duration") is not None:
        context["ltx_duration_seconds"] = metadata.get("requested_duration")
    prev_task_id = str(metadata.get("ltx_prev_task_id") or "").strip()
    if prev_task_id:
        context["ltx_prev_task_id"] = prev_task_id
    chain_task_ids = normalize_ltx_video_chain_task_ids(
        metadata.get("ltx_chain_task_ids")
    )
    if chain_task_ids:
        context["ltx_chain_task_ids"] = chain_task_ids
    lora_items = metadata.get("lora_items")
    if isinstance(lora_items, list) and lora_items:
        context["lora_items"] = lora_items
    lora_name = str(metadata.get("lora_name") or "").strip()
    if lora_name:
        context["lora_name"] = lora_name
    if metadata.get("lora_strength") is not None:
        context["lora_strength"] = metadata.get("lora_strength")
    return context


def merge_ltx_history_context_into_extra_outputs(
    *,
    task_type: str | None,
    extra_outputs: dict | None,
    metadata: dict | None,
) -> dict[str, object] | None:
    if task_type != MODE_LTX_VIDEO:
        return extra_outputs
    context = build_ltx_history_context_from_metadata(metadata)
    if not context and not extra_outputs:
        return extra_outputs
    merged = dict(extra_outputs or {})
    if context:
        merged[LTX_HISTORY_CONTEXT_KEY] = context
    return merged


def build_ltx_chain_prompt_summary(histories: list[History]) -> str:
    segments: list[str] = []
    for index, history in enumerate(histories, start=1):
        prompt = str(getattr(history, "prompt", "") or "").strip() or "（未填写提示词）"
        segments.append(f"【第 {index} 段】\n{prompt}")
    return "\n\n".join(segments).strip()


def build_ltx_stitched_extra_outputs(
    *,
    chain_task_ids: list[str],
    source_task_id: str | None,
) -> dict[str, object]:
    normalized_chain = normalize_ltx_video_chain_task_ids(chain_task_ids)
    stitched_payload: dict[str, object] = {
        "segment_count": len(normalized_chain),
        "ltx_chain_task_ids": normalized_chain,
    }
    normalized_source_task_id = str(source_task_id or "").strip()
    if normalized_source_task_id:
        stitched_payload["source_task_id"] = normalized_source_task_id
    return {LTX_STITCH_RESULT_KEY: stitched_payload}


def _resolve_latest_history_value(histories: list[History], field_name: str):
    for history in reversed(histories):
        value = getattr(history, field_name, None)
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        return value
    return None


def _sum_history_int_values(histories: list[History], field_name: str) -> int | None:
    total = sum(int(getattr(history, field_name, 0) or 0) for history in histories)
    return total or None


def _build_stitched_ltx_history(
    *,
    histories: list[History],
    user_id: int,
    task_id: str,
    output_file: str,
    source_task_id: str | None,
    source: str,
) -> History:
    chain_task_ids = [
        str(getattr(history, "task_id", "") or "").strip()
        for history in histories
        if str(getattr(history, "task_id", "") or "").strip()
    ]
    return History(
        user_id=user_id,
        task_id=task_id,
        type=MODE_LTX_VIDEO,
        prompt=build_ltx_chain_prompt_summary(histories),
        output_file=output_file,
        extra_outputs=build_ltx_stitched_extra_outputs(
            chain_task_ids=chain_task_ids,
            source_task_id=source_task_id,
        ),
        billing_resolution=_resolve_latest_history_value(histories, "billing_resolution"),
        width=_resolve_latest_history_value(histories, "width"),
        height=_resolve_latest_history_value(histories, "height"),
        duration=_sum_history_int_values(histories, "duration"),
        requested_duration=_sum_history_int_values(histories, "requested_duration"),
        allow_contribute=all(
            getattr(history, "allow_contribute", True) is not False
            for history in histories
        ),
        source=source,
    )


async def stitch_ltx_histories_and_create_history(
    *,
    histories: list[History],
    user_id: int,
    source_task_id: str | None,
    source: str,
    session=None,
) -> LtxVideoStitchedHistoryResult:
    stitched_video = await stitch_history_videos(histories)
    stitched_task_id = f"ltx_chain_{uuid.uuid4().hex[:24]}"
    output_object_name = f"{user_id}/output_images/{stitched_task_id}.mp4"
    output_file = storage.upload_bytes(
        stitched_video,
        output_object_name,
        content_type="video/mp4",
    )
    if not output_file:
        raise LtxVideoPersistenceError("拼接视频上传失败，请稍后再试")

    stitched_history = _build_stitched_ltx_history(
        histories=histories,
        user_id=user_id,
        task_id=stitched_task_id,
        output_file=output_file,
        source_task_id=source_task_id,
        source=source,
    )

    async def _persist(active_session):
        active_session.add(stitched_history)
        await active_session.commit()
        await active_session.refresh(stitched_history)

    if session is not None:
        await _persist(session)
    else:
        async with AsyncSessionLocal() as new_session:
            await _persist(new_session)

    return LtxVideoStitchedHistoryResult(
        video_bytes=stitched_video,
        task_id=stitched_task_id,
        task_type=str(stitched_history.type or ""),
        prompt=str(stitched_history.prompt or ""),
        output_file=str(stitched_history.output_file or ""),
        extra_outputs=dict(stitched_history.extra_outputs or {}),
        allow_contribute=getattr(stitched_history, "allow_contribute", True) is not False,
        segment_count=len(histories),
        history=stitched_history,
    )
