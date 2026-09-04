from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
import uuid
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy import select, text
from PIL import Image, ImageOps

from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.domain_config.minimax_h3 import (
    MINIMAX_H3_ASPECT_RATIOS,
    MINIMAX_H3_EXECUTION_TASK_TYPE_INPUT,
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
)
from src.services.minimax_h3_history_context_service import (
    extract_minimax_h3_history_context,
    normalize_minimax_h3_chain_task_ids,
    resolve_valid_minimax_h3_history_context,
)
from src.services.storage import storage
from src.core import user_core
from src.media_paths import resolve_storage_object
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.qqcc_video_chain_stitch_service import stitch_qqcc_video_segments
from src.services.user_visible_generation_presenter import present_user_prompt


MINIMAX_H3_STITCH_RESULT_KEY = "_minimax_h3_chain_stitch"
MINIMAX_H3_EXTENSION_SOURCE_TASK_TYPES = frozenset(
    {MINIMAX_H3_I2V, MINIMAX_H3_FLF2V, MINIMAX_H3_REF2V}
)
MINIMAX_H3_EXTENSION_TARGET_TASK_TYPES = frozenset({MINIMAX_H3_REF2V, MINIMAX_H3_FLF2V})


class MiniMaxH3ExtensionError(ValueError):
    pass


class MiniMaxH3PersistenceError(MiniMaxH3ExtensionError):
    pass


@dataclass(frozen=True, slots=True)
class MiniMaxH3ExtensionPreparation:
    history: History
    images: tuple[str, ...]
    reference_video: str | None
    execution_task_type: str | None
    aspect_ratio: str | None
    metadata: dict[str, object]
    allow_contribute: bool


@dataclass(frozen=True, slots=True)
class MiniMaxH3ExtensionFsmSeed:
    fsm_data: dict[str, object]
    history: History


@dataclass(frozen=True, slots=True)
class MiniMaxH3StitchedHistoryResult:
    video_bytes: bytes
    history: History
    segment_count: int


def is_minimax_h3_stitched_result(extra_outputs: dict | None) -> bool:
    return isinstance(extra_outputs, dict) and isinstance(
        extra_outputs.get(MINIMAX_H3_STITCH_RESULT_KEY), dict
    )


def resolve_minimax_h3_stitched_segment_count(
    extra_outputs: dict | None,
) -> int | None:
    if not is_minimax_h3_stitched_result(extra_outputs):
        return None
    payload = extra_outputs[MINIMAX_H3_STITCH_RESULT_KEY]
    try:
        count = int(payload.get("segment_count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        return count
    return (
        len(normalize_minimax_h3_chain_task_ids(payload.get("chain_task_ids"))) or None
    )


def resolve_minimax_h3_segment_index(extra_outputs: dict | None) -> int | None:
    if is_minimax_h3_stitched_result(extra_outputs):
        return None
    context = extract_minimax_h3_history_context(extra_outputs)
    if not context:
        return None
    chain_task_ids = normalize_minimax_h3_chain_task_ids(context.get("chain_task_ids"))
    return len(chain_task_ids) + 1


def resolve_minimax_h3_last_frame_output_file(history: History) -> str:
    extra_outputs = getattr(history, "extra_outputs", None)
    if is_minimax_h3_stitched_result(extra_outputs):
        raise MiniMaxH3ExtensionError("拼接结果不能继续扩展，请选择最后一个生成段。")
    last_frame = (
        extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
    )
    output_file = last_frame.get("path") if isinstance(last_frame, dict) else None
    if not output_file:
        raise MiniMaxH3ExtensionError("这条记录没有可用的尾帧图片，无法扩展生成。")
    return str(output_file)


def build_minimax_h3_full_chain_task_ids(history: History) -> list[str]:
    context = resolve_valid_minimax_h3_history_context(
        task_type=getattr(history, "type", None),
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    if not context:
        raise MiniMaxH3ExtensionError("H3 记录缺少有效的生成上下文，无法扩展。")
    current_task_id = str(getattr(history, "task_id", "") or "").strip()
    if not current_task_id:
        raise MiniMaxH3ExtensionError("H3 记录缺少任务编号，无法扩展。")
    return [
        *normalize_minimax_h3_chain_task_ids(context.get("chain_task_ids")),
        current_task_id,
    ]


def resolve_minimax_h3_extension_aspect_ratio(history: History) -> str:
    context = resolve_valid_minimax_h3_history_context(
        task_type=getattr(history, "type", None),
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    context_aspect = str((context or {}).get("aspect_ratio") or "").strip()
    if context_aspect in MINIMAX_H3_ASPECT_RATIOS:
        return context_aspect
    try:
        width = int(getattr(history, "width", 0) or 0)
        height = int(getattr(history, "height", 0) or 0)
    except (TypeError, ValueError):
        width = height = 0
    if width <= 0 or height <= 0:
        return "16:9"
    source_ratio = width / height
    return min(
        MINIMAX_H3_ASPECT_RATIOS,
        key=lambda name: abs(MINIMAX_H3_ASPECT_RATIOS[name] - source_ratio),
    )


async def load_owned_minimax_h3_history_for_internal_user(
    *, task_id: str, internal_user_id: int, session=None
) -> History:
    async def _load(active_session):
        result = await active_session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == internal_user_id,
            )
        )
        return result.scalar_one_or_none()

    if session is not None:
        history = await _load(session)
    else:
        async with AsyncSessionLocal() as active_session:
            history = await _load(active_session)
    if history is None:
        raise MiniMaxH3ExtensionError("未找到对应的视频记录，或该记录不属于您。")
    if (
        str(getattr(history, "type", "") or "")
        not in MINIMAX_H3_EXTENSION_SOURCE_TASK_TYPES
    ):
        raise MiniMaxH3ExtensionError("当前仅支持 H3 图像模式结果的扩展生成。")
    if is_minimax_h3_stitched_result(getattr(history, "extra_outputs", None)):
        raise MiniMaxH3ExtensionError("拼接结果不能继续扩展，请选择最后一个生成段。")
    return history


async def prepare_minimax_h3_web_extension(
    *,
    prev_task_id: str,
    internal_user_id: int,
    target_task_type: str,
    client_images: list[str],
    session=None,
    frame_aspect_validator=None,
) -> MiniMaxH3ExtensionPreparation:
    if target_task_type not in MINIMAX_H3_EXTENSION_TARGET_TASK_TYPES:
        raise MiniMaxH3ExtensionError("H3 扩展仅支持直接续写或添加终止帧。")
    expected_client_images = 0 if target_task_type == MINIMAX_H3_REF2V else 1
    if len(client_images) != expected_client_images:
        raise MiniMaxH3ExtensionError(
            "视频参考续写不能上传首帧。"
            if expected_client_images == 0
            else "添加终止帧时只能上传一张终止帧。"
        )
    history = await load_owned_minimax_h3_history_for_internal_user(
        task_id=prev_task_id,
        internal_user_id=internal_user_id,
        session=session,
    )
    last_frame = resolve_minimax_h3_last_frame_output_file(history)
    if target_task_type == MINIMAX_H3_FLF2V:
        frame_aspect_validator = (
            frame_aspect_validator or validate_minimax_h3_storage_frame_aspects
        )
        await frame_aspect_validator([last_frame, client_images[0]])
    full_chain = build_minimax_h3_full_chain_task_ids(history)
    return MiniMaxH3ExtensionPreparation(
        history=history,
        images=tuple([last_frame, *client_images]),
        reference_video=None,
        execution_task_type=(
            MINIMAX_H3_I2V if target_task_type == MINIMAX_H3_REF2V else None
        ),
        aspect_ratio=(
            resolve_minimax_h3_extension_aspect_ratio(history)
            if target_task_type == MINIMAX_H3_REF2V
            else None
        ),
        metadata={
            "minimax_h3_prev_task_id": prev_task_id,
            "minimax_h3_chain_task_ids": full_chain,
        },
        allow_contribute=False,
    )


def _decode_image_dimensions(payload: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(payload)) as image:
            normalized = ImageOps.exif_transpose(image)
            dimensions = (int(normalized.width), int(normalized.height))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise MiniMaxH3ExtensionError("无法读取扩展帧尺寸，请重新上传终止帧。") from exc
    if dimensions[0] <= 0 or dimensions[1] <= 0:
        raise MiniMaxH3ExtensionError("扩展帧尺寸无效，请重新上传终止帧。")
    return dimensions


async def validate_minimax_h3_storage_frame_aspects(
    object_keys: list[str] | tuple[str, ...],
    *,
    relative_tolerance: float = 0.01,
) -> tuple[tuple[int, int], ...]:
    dimensions: list[tuple[int, int]] = []
    for object_key in object_keys:
        bucket_name, object_name = resolve_storage_object(str(object_key))
        try:
            payload = await asyncio.to_thread(
                storage.get_file_bytes,
                object_name,
                bucket_name,
            )
        except Exception as exc:
            raise MiniMaxH3ExtensionError(
                "扩展帧暂时无法读取，请重新上传终止帧。"
            ) from exc
        if not payload:
            raise MiniMaxH3ExtensionError("扩展帧内容为空，请重新上传终止帧。")
        dimensions.append(_decode_image_dimensions(payload))
    first_width, first_height = dimensions[0]
    last_width, last_height = dimensions[-1]
    first_ratio = first_width / first_height
    last_ratio = last_width / last_height
    if abs(first_ratio - last_ratio) / first_ratio > relative_tolerance:
        raise MiniMaxH3ExtensionError("终止帧比例需与上一段尾帧一致，请重新上传。")
    return tuple(dimensions)


async def prepare_minimax_h3_extension_fsm_data(
    *,
    prev_task_id: str,
    telegram_user_id: int,
    username: str | None,
) -> MiniMaxH3ExtensionFsmSeed:
    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        telegram_user_id,
        username,
    )
    history = await load_owned_minimax_h3_history_for_internal_user(
        task_id=prev_task_id,
        internal_user_id=internal_user.id,
    )
    context = resolve_valid_minimax_h3_history_context(
        task_type=history.type,
        extra_outputs=getattr(history, "extra_outputs", None),
    )
    if not context:
        raise MiniMaxH3ExtensionError("H3 记录缺少有效的生成上下文，无法扩展。")
    last_frame = resolve_minimax_h3_last_frame_output_file(history)
    frame_bucket, frame_object = resolve_storage_object(last_frame)
    frame_suffix = Path(last_frame).suffix or ".png"
    local_frame_path = Path(FSM_TEMP_DIR) / (
        f"{uuid.uuid4().hex}_h3_extension_start{frame_suffix}"
    )
    local_frame_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(
            storage.download_file,
            frame_bucket,
            frame_object,
            str(local_frame_path),
        )
    except BaseException:
        local_frame_path.unlink(missing_ok=True)
        raise
    return MiniMaxH3ExtensionFsmSeed(
        history=history,
        fsm_data={
            "mode": "ref2v",
            "duration": int(context["requested_duration"]),
            "preset": str(context["resolution_preset"]),
            "aspect": resolve_minimax_h3_extension_aspect_ratio(history),
            "images": [str(local_frame_path)],
            "reference_video": None,
            MINIMAX_H3_EXECUTION_TASK_TYPE_INPUT: MINIMAX_H3_I2V,
            "extension_start_frame": str(local_frame_path),
            "reference_descriptions": [],
            "reference_audio": None,
            "is_extension": True,
            "extension_prev_task_id": prev_task_id,
            "minimax_h3_chain_task_ids": build_minimax_h3_full_chain_task_ids(history),
            "extension_allow_contribute": False,
        },
    )


def _validate_ordered_chain(histories: list[History], task_ids: list[str]) -> None:
    if len(histories) != len(task_ids):
        raise MiniMaxH3ExtensionError("H3 扩展链存在缺失记录，无法继续操作。")
    for index, history in enumerate(histories):
        if str(getattr(history, "task_id", "") or "") != task_ids[index]:
            raise MiniMaxH3ExtensionError("H3 扩展链顺序异常，无法继续操作。")
        context = resolve_valid_minimax_h3_history_context(
            task_type=getattr(history, "type", None),
            extra_outputs=getattr(history, "extra_outputs", None),
        )
        if not context:
            raise MiniMaxH3ExtensionError("H3 扩展链包含无效上下文。")
        expected_ancestors = task_ids[:index]
        actual_ancestors = normalize_minimax_h3_chain_task_ids(
            context.get("chain_task_ids")
        )
        if actual_ancestors != expected_ancestors:
            raise MiniMaxH3ExtensionError("H3 扩展链上下文不连续。")
        expected_prev = task_ids[index - 1] if index else ""
        if str(context.get("prev_task_id") or "") != expected_prev:
            raise MiniMaxH3ExtensionError("H3 扩展链父记录不连续。")


async def load_minimax_h3_chain_for_internal_user(
    *, task_id: str, internal_user_id: int, session=None
) -> list[History]:
    current = await load_owned_minimax_h3_history_for_internal_user(
        task_id=task_id,
        internal_user_id=internal_user_id,
        session=session,
    )
    task_ids = build_minimax_h3_full_chain_task_ids(current)

    async def _load(active_session):
        result = await active_session.execute(
            select(History).where(
                History.user_id == internal_user_id,
                History.task_id.in_(task_ids),
            )
        )
        return list(result.scalars().all())

    if session is not None:
        unordered = await _load(session)
    else:
        async with AsyncSessionLocal() as active_session:
            unordered = await _load(active_session)
    by_task_id = {str(item.task_id or ""): item for item in unordered}
    histories = [by_task_id[item] for item in task_ids if item in by_task_id]
    _validate_ordered_chain(histories, task_ids)
    return histories


def build_minimax_h3_stitched_extra_outputs(
    *, chain_task_ids: list[str], source_task_id: str
) -> dict[str, object]:
    return {
        MINIMAX_H3_STITCH_RESULT_KEY: {
            "version": 1,
            "segment_count": len(chain_task_ids),
            "chain_task_ids": list(chain_task_ids),
            "source_task_id": source_task_id,
        }
    }


def _stitched_task_id(*, user_id: int, chain_task_ids: list[str]) -> str:
    digest = hashlib.sha256(
        f"{user_id}:{'|'.join(chain_task_ids)}".encode("utf-8")
    ).hexdigest()[:24]
    return f"minimax_h3_chain_{digest}"


def _build_chain_prompt(histories: list[History]) -> str:
    return "\n\n".join(
        f"【第 {index} 段】\n{str(history.prompt or '').strip() or '（未填写提示词）'}"
        for index, history in enumerate(histories, start=1)
    )


async def _acquire_minimax_h3_stitch_lock(
    session,
    *,
    user_id: int,
    task_id: str,
) -> None:
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:stitch_owner, 0))"),
        {"stitch_owner": f"minimax-h3-stitch:{user_id}:{task_id}"},
    )


async def stitch_minimax_h3_history_videos(histories: list[History]) -> bytes:
    """Normalize every segment to the first canvas/fps/audio before concatenation."""

    payloads: list[bytes] = []
    for history in histories:
        output_file = str(getattr(history, "output_file", "") or "").strip()
        if not output_file:
            raise MiniMaxH3ExtensionError("存在缺少视频文件的 H3 记录，无法拼接。")
        bucket_name, object_name = resolve_storage_object(output_file)
        payload = await asyncio.to_thread(
            storage.get_file_bytes,
            object_name,
            bucket_name,
        )
        if not payload:
            raise MiniMaxH3ExtensionError("存在无法读取的视频片段，无法拼接。")
        payloads.append(payload)
    return await stitch_qqcc_video_segments(payloads)


async def stitch_minimax_h3_histories_and_create_history(
    *,
    histories: list[History],
    user_id: int,
    source_task_id: str,
    source: str,
    session=None,
    stitch_func=stitch_minimax_h3_history_videos,
) -> MiniMaxH3StitchedHistoryResult:
    if len(histories) < 2:
        raise MiniMaxH3ExtensionError("至少需要两段 H3 视频才能执行拼接。")
    task_ids = [str(history.task_id or "") for history in histories]
    _validate_ordered_chain(histories, task_ids)
    task_id = _stitched_task_id(user_id=user_id, chain_task_ids=task_ids)
    first = histories[0]
    combined_prompt = _build_chain_prompt(histories)
    stitched_allow_contribute = (
        getattr(first, "allow_contribute", True) is not False
    )

    async def _find_existing(active_session):
        result = await active_session.execute(
            select(History).where(
                History.user_id == user_id,
                History.task_id == task_id,
            )
        )
        return result.scalar_one_or_none()

    active_session = session
    owns_session = active_session is None
    if owns_session:
        active_session = AsyncSessionLocal()
    try:
        await _acquire_minimax_h3_stitch_lock(
            active_session,
            user_id=user_id,
            task_id=task_id,
        )
        existing = await _find_existing(active_session)
        if existing is not None:
            if (
                existing.prompt != combined_prompt
                or existing.allow_contribute is not stitched_allow_contribute
            ):
                existing.prompt = combined_prompt
                existing.allow_contribute = stitched_allow_contribute
                await active_session.commit()
                await active_session.refresh(existing)
            bucket_name, object_name = resolve_storage_object(existing.output_file)
            existing_bytes = await asyncio.to_thread(
                storage.get_file_bytes,
                object_name,
                bucket_name,
            )
            return MiniMaxH3StitchedHistoryResult(
                video_bytes=existing_bytes,
                history=existing,
                segment_count=len(histories),
            )
        stitched_video = await stitch_func(histories)
        output_file = await asyncio.to_thread(
            storage.upload_bytes,
            stitched_video,
            f"task-results/{task_id}/primary.mp4",
            content_type="video/mp4",
        )
        if not output_file:
            raise MiniMaxH3PersistenceError("拼接视频上传失败，请稍后再试。")
        history = History(
            user_id=user_id,
            task_id=task_id,
            type=MINIMAX_H3_I2V,
            prompt=combined_prompt,
            output_file=output_file,
            extra_outputs=build_minimax_h3_stitched_extra_outputs(
                chain_task_ids=task_ids,
                source_task_id=source_task_id,
            ),
            billing_resolution=getattr(first, "billing_resolution", None),
            width=getattr(first, "width", None),
            height=getattr(first, "height", None),
            duration=sum(int(getattr(item, "duration", 0) or 0) for item in histories)
            or None,
            requested_duration=sum(
                int(getattr(item, "requested_duration", 0) or 0) for item in histories
            )
            or None,
            allow_contribute=stitched_allow_contribute,
            source=source,
        )
        active_session.add(history)
        await active_session.commit()
        await active_session.refresh(history)
        return MiniMaxH3StitchedHistoryResult(
            video_bytes=stitched_video,
            history=history,
            segment_count=len(histories),
        )
    finally:
        if owns_session:
            await active_session.close()


def present_minimax_h3_stitched_prompt(history: History) -> str:
    return present_user_prompt(
        history.prompt,
        extra_outputs=getattr(history, "extra_outputs", None),
    ).prompt
