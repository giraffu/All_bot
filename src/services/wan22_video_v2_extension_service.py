import asyncio
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from src.constants import MODE_WAN22_VIDEO_V2
from src.core.media_paths import resolve_storage_object
from src.core import user_core
from src.core.video_billing import resolve_apply_prompt_and_requested_duration
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.lora_mapping import extract_prompt_lora_context
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.services.storage import storage
from src.domain_config.wan22_aio_video import normalize_wan22_video_v2_chain_task_ids
from src.domain_config.wan22_aio_video import (
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    is_wan22_chain_history_task_type,
    normalize_wan22_video_v2_resolution_preset,
)

WAN22_HISTORY_CONTEXT_KEY = "_wan22_context"
WAN22_STITCH_RESULT_KEY = "wan22_chain_stitch"


class Wan22VideoV2ExtensionError(Exception):
    """Raised when WAN2.2 extension or stitching prerequisites are not met."""


class Wan22VideoV2MissingPreviousSegmentError(Wan22VideoV2ExtensionError):
    """Raised when a regeneration callback cannot recover its previous segment."""


class Wan22VideoV2PersistenceError(Wan22VideoV2ExtensionError):
    """Raised when a stitched WAN2.2 result cannot be persisted."""


@dataclass(frozen=True)
class Wan22StitchedHistoryResult:
    video_bytes: bytes
    task_id: str
    task_type: str
    prompt: str
    output_file: str
    extra_outputs: dict[str, object]
    allow_contribute: bool
    segment_count: int
    history: History


@dataclass(frozen=True)
class Wan22ExtensionFsmSeed:
    fsm_data: dict[str, object]
    history: History
    base_task_id: str
    merged_meta: dict[str, object]


@dataclass(frozen=True)
class Wan22RegenerationFsmSeed:
    fsm_data: dict[str, object]
    current_history: History
    prev_history: History
    current_task_id: str
    prev_task_id: str
    merged_meta: dict[str, object]


@dataclass(frozen=True)
class Wan22StitchPlan:
    histories: list[History]
    internal_user_id: int
    source_task_id: str
    full_task_ids: list[str]


LoadOwnedWan22HistoryFunc = Callable[..., Awaitable[History]]
DownloadLastFrameFunc = Callable[..., Awaitable[str]]
DownloadHistoryInputFileFunc = Callable[..., Awaitable[str]]


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
    if not is_wan22_chain_history_task_type(history.type):
        raise Wan22VideoV2ExtensionError("当前仅支持图生视频链路记录的扩展生成。")
    return history


async def load_owned_wan22_history_for_internal_user(
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
        raise Wan22VideoV2ExtensionError("未找到对应的视频记录，或该记录不属于您。")
    if not is_wan22_chain_history_task_type(history.type):
        raise Wan22VideoV2ExtensionError("当前仅支持图生视频链路记录的扩展生成。")
    return history


def resolve_last_frame_output_file(history: History) -> str:
    extra_outputs = history.extra_outputs or {}
    last_frame = extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
    output_file = last_frame.get("path") if isinstance(last_frame, dict) else None
    if not output_file:
        raise Wan22VideoV2ExtensionError("这条记录没有可用的尾帧图片，请先重新生成该段视频。")
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


def extract_wan22_history_context(extra_outputs: dict | None) -> dict[str, object]:
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(WAN22_HISTORY_CONTEXT_KEY)
    if not isinstance(context, dict):
        return {}
    return dict(context)


def merge_wan22_history_context_into_meta(
    history: History,
    meta: dict[str, Any] | None,
) -> dict[str, object]:
    return {
        **extract_wan22_history_context(getattr(history, "extra_outputs", None)),
        **dict(meta or {}),
    }


def resolve_wan22_history_duration_seconds(
    history: History,
    meta: dict[str, Any] | None,
) -> int:
    meta = meta or {}
    raw_duration = (
        meta.get("wan22_duration_seconds")
        or getattr(history, "requested_duration", None)
        or getattr(history, "duration", None)
    )
    try:
        duration = int(raw_duration)
    except (TypeError, ValueError):
        duration = 5
    if duration not in {5, 8, 10}:
        duration = 5
    return duration


def resolve_reusable_wan22_history_prompt_and_lora(
    history: History,
    meta: dict[str, Any] | None,
) -> tuple[str, str | None, float]:
    meta = meta or {}
    prompt, _requested_duration = resolve_apply_prompt_and_requested_duration(
        getattr(history, "type", None),
        getattr(history, "prompt", None),
        getattr(history, "requested_duration", None),
    )
    prompt, parsed_lora_name, parsed_lora_strength = extract_prompt_lora_context(prompt)
    lora_name = str(meta.get("lora_name") or parsed_lora_name or "").strip() or None
    lora_strength = meta.get("lora_strength")
    try:
        normalized_lora_strength = float(lora_strength)
    except (TypeError, ValueError):
        normalized_lora_strength = parsed_lora_strength or 1.0
    return prompt, lora_name, normalized_lora_strength


async def prepare_wan22_extension_fsm_data(
    *,
    base_task_id: str,
    telegram_user_id: int,
    username: str | None,
    message_meta: dict[str, Any] | None = None,
    load_history_func: LoadOwnedWan22HistoryFunc = load_owned_wan22_history,
    download_last_frame_func: DownloadLastFrameFunc | None = None,
) -> Wan22ExtensionFsmSeed:
    download_last_frame_func = download_last_frame_func or download_last_frame_to_fsm_temp
    history = await load_history_func(
        task_id=base_task_id,
        telegram_user_id=telegram_user_id,
        username=username,
    )
    merged_meta = merge_wan22_history_context_into_meta(history, message_meta)
    start_image_path = await download_last_frame_func(history=history)
    fsm_data: dict[str, object] = {
        "start_image_path": start_image_path,
        "end_image_path": None,
        "use_end_frame": False,
        "resolution_preset": resolve_extension_resolution_preset(merged_meta),
        "duration": resolve_wan22_history_duration_seconds(history, merged_meta),
        "prompt": "",
        "negative_prompt": "",
        "extension_prev_task_id": base_task_id,
        "extension_task_type": getattr(history, "type", None),
        "lora_name": str(merged_meta.get("lora_name") or "").strip(),
        "lora_strength": merged_meta.get("lora_strength"),
        "chain_task_ids": build_full_chain_task_ids(
            chain_task_ids=resolve_extension_chain_task_ids(merged_meta),
            current_task_id=base_task_id,
        ),
    }
    return Wan22ExtensionFsmSeed(
        fsm_data=fsm_data,
        history=history,
        base_task_id=base_task_id,
        merged_meta=merged_meta,
    )


async def prepare_wan22_regeneration_fsm_data(
    *,
    current_task_id: str,
    telegram_user_id: int,
    username: str | None,
    message_meta: dict[str, Any] | None = None,
    load_history_func: LoadOwnedWan22HistoryFunc = load_owned_wan22_history,
    download_last_frame_func: DownloadLastFrameFunc | None = None,
    download_history_input_file_func: DownloadHistoryInputFileFunc | None = None,
) -> Wan22RegenerationFsmSeed:
    download_last_frame_func = download_last_frame_func or download_last_frame_to_fsm_temp
    download_history_input_file_func = (
        download_history_input_file_func or download_history_input_file_to_fsm_temp
    )
    current_history = await load_history_func(
        task_id=current_task_id,
        telegram_user_id=telegram_user_id,
        username=username,
    )
    merged_meta = merge_wan22_history_context_into_meta(current_history, message_meta)
    prev_task_id = str(merged_meta.get("wan22_prev_task_id") or "").strip()
    if not prev_task_id:
        raise Wan22VideoV2MissingPreviousSegmentError("记录已失效，请重新生成后再试")

    prev_history = await load_history_func(
        task_id=prev_task_id,
        telegram_user_id=telegram_user_id,
        username=username,
    )
    start_image_path = await download_last_frame_func(
        history=prev_history,
        name_hint="wan22_video_v2_regenerate_start",
    )
    use_end_frame = bool(merged_meta.get("wan22_use_end_frame"))
    end_image_path = None
    if use_end_frame:
        end_image_path = await download_history_input_file_func(
            history=current_history,
            index=1,
            name_hint="wan22_video_v2_regenerate_end",
        )

    if getattr(current_history, "type", None) == MODE_WAN22_VIDEO_V2:
        prompt = str(getattr(current_history, "prompt", "") or "").strip()
        lora_name = None
        lora_strength = None
    else:
        prompt, lora_name, lora_strength = resolve_reusable_wan22_history_prompt_and_lora(
            current_history,
            merged_meta,
        )

    fsm_data: dict[str, object] = {
        "start_image_path": start_image_path,
        "end_image_path": end_image_path,
        "use_end_frame": use_end_frame,
        "resolution_preset": resolve_extension_resolution_preset(merged_meta),
        "duration": resolve_wan22_history_duration_seconds(
            current_history,
            merged_meta,
        ),
        "prompt": prompt,
        "prefill_prompt": prompt,
        "negative_prompt": str(merged_meta.get("wan22_negative_prompt") or "").strip(),
        "extension_prev_task_id": prev_task_id,
        "extension_task_type": getattr(current_history, "type", None),
        "lora_name": lora_name,
        "lora_strength": lora_strength,
        "chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
            merged_meta.get("wan22_chain_task_ids")
        ),
    }
    return Wan22RegenerationFsmSeed(
        fsm_data=fsm_data,
        current_history=current_history,
        prev_history=prev_history,
        current_task_id=current_task_id,
        prev_task_id=prev_task_id,
        merged_meta=merged_meta,
    )


async def build_wan22_stitch_plan(
    *,
    current_task_id: str,
    telegram_user_id: int,
    username: str | None,
    message_meta: dict[str, Any] | None = None,
    load_history_func: LoadOwnedWan22HistoryFunc = load_owned_wan22_history,
) -> Wan22StitchPlan:
    current_history = await load_history_func(
        task_id=current_task_id,
        telegram_user_id=telegram_user_id,
        username=username,
    )
    merged_meta = merge_wan22_history_context_into_meta(current_history, message_meta)
    full_task_ids = build_full_chain_task_ids(
        chain_task_ids=normalize_wan22_video_v2_chain_task_ids(
            merged_meta.get("wan22_chain_task_ids")
        ),
        current_task_id=current_task_id,
    )
    if len(full_task_ids) < 2:
        raise Wan22VideoV2ExtensionError("至少需要两段视频才能完成拼接")

    history_cache = {current_task_id: current_history}
    histories: list[History] = []
    for task_id in full_task_ids:
        history = history_cache.get(task_id)
        if history is None:
            history = await load_history_func(
                task_id=task_id,
                telegram_user_id=telegram_user_id,
                username=username,
            )
            history_cache[task_id] = history
        histories.append(history)

    internal_user_id = int(getattr(histories[0], "user_id", 0) or 0)
    if not internal_user_id:
        raise Wan22VideoV2ExtensionError("未找到用户信息，无法保存拼接结果。")

    return Wan22StitchPlan(
        histories=histories,
        internal_user_id=internal_user_id,
        source_task_id=current_task_id,
        full_task_ids=full_task_ids,
    )


def is_wan22_stitched_result(extra_outputs: dict | None) -> bool:
    if not isinstance(extra_outputs, dict):
        return False
    return isinstance(extra_outputs.get(WAN22_STITCH_RESULT_KEY), dict)


def resolve_wan22_stitched_segment_count(extra_outputs: dict | None) -> int | None:
    if not isinstance(extra_outputs, dict):
        return None
    stitched_payload = extra_outputs.get(WAN22_STITCH_RESULT_KEY)
    if not isinstance(stitched_payload, dict):
        return None
    raw_count = stitched_payload.get("segment_count")
    try:
        normalized_count = int(raw_count)
    except (TypeError, ValueError):
        normalized_count = 0
    if normalized_count > 0:
        return normalized_count
    chain_task_ids = stitched_payload.get("wan22_chain_task_ids")
    if isinstance(chain_task_ids, list):
        normalized_chain = [str(task_id or "").strip() for task_id in chain_task_ids]
        normalized_chain = [task_id for task_id in normalized_chain if task_id]
        if normalized_chain:
            return len(normalized_chain)
    return None


def resolve_wan22_segment_index(extra_outputs: dict | None) -> int | None:
    if is_wan22_stitched_result(extra_outputs):
        return None
    context = extract_wan22_history_context(extra_outputs)
    if not context:
        return None
    chain_task_ids = normalize_wan22_video_v2_chain_task_ids(
        context.get("wan22_chain_task_ids")
    )
    if chain_task_ids:
        return len(chain_task_ids) + 1
    prev_task_id = str(context.get("wan22_prev_task_id") or "").strip()
    if prev_task_id:
        return 2
    return 1


def build_wan22_history_context_from_metadata(metadata: dict | None) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    context: dict[str, object] = {}
    resolution_preset = normalize_wan22_video_v2_resolution_preset(
        metadata.get("wan22_resolution_preset") or metadata.get("resolution_preset")
    )
    context["wan22_resolution_preset"] = resolution_preset
    negative_prompt = str(metadata.get("wan22_negative_prompt") or "").strip()
    if negative_prompt:
        context["wan22_negative_prompt"] = negative_prompt
    context["wan22_use_end_frame"] = bool(metadata.get("wan22_use_end_frame"))
    model_profile = str(metadata.get("wan22_model_profile") or "").strip()
    if model_profile:
        context["wan22_model_profile"] = model_profile
    lora_name = str(metadata.get("lora_name") or "").strip()
    if lora_name:
        context["lora_name"] = lora_name
    if metadata.get("lora_strength") is not None:
        context["lora_strength"] = metadata.get("lora_strength")
    prev_task_id = str(metadata.get("wan22_prev_task_id") or "").strip()
    if prev_task_id:
        context["wan22_prev_task_id"] = prev_task_id
    chain_task_ids = normalize_wan22_video_v2_chain_task_ids(
        metadata.get("wan22_chain_task_ids")
    )
    if chain_task_ids:
        context["wan22_chain_task_ids"] = chain_task_ids
    return context


def merge_wan22_history_context_into_extra_outputs(
    *,
    task_type: str | None,
    extra_outputs: dict | None,
    metadata: dict | None,
) -> dict[str, object] | None:
    if not is_wan22_chain_history_task_type(task_type):
        return extra_outputs
    context = build_wan22_history_context_from_metadata(metadata)
    if not context and not extra_outputs:
        return extra_outputs
    merged = dict(extra_outputs or {})
    if context:
        merged[WAN22_HISTORY_CONTEXT_KEY] = context
    return merged


def build_wan22_chain_prompt_summary(histories: list[History]) -> str:
    segments: list[str] = []
    for index, history in enumerate(histories, start=1):
        prompt = str(getattr(history, "prompt", "") or "").strip() or "（未填写提示词）"
        segments.append(f"【第 {index} 段】\n{prompt}")
    return "\n\n".join(segments).strip()


def build_wan22_stitched_extra_outputs(
    *,
    chain_task_ids: list[str],
    source_task_id: str | None,
) -> dict[str, object]:
    normalized_chain = [
        str(task_id or "").strip() for task_id in chain_task_ids if str(task_id or "").strip()
    ]
    stitched_payload: dict[str, object] = {
        "segment_count": len(normalized_chain),
        "wan22_chain_task_ids": normalized_chain,
    }
    normalized_source_task_id = str(source_task_id or "").strip()
    if normalized_source_task_id:
        stitched_payload["source_task_id"] = normalized_source_task_id
    return {WAN22_STITCH_RESULT_KEY: stitched_payload}


def _resolve_stitched_history_type(histories: list[History]) -> str:
    if histories:
        stitched_type = str(getattr(histories[-1], "type", "") or "").strip()
        if stitched_type:
            return stitched_type
    return "wan22_video_v2"


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


def _build_stitched_history(
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
        type=_resolve_stitched_history_type(histories),
        prompt=build_wan22_chain_prompt_summary(histories),
        output_file=output_file,
        extra_outputs=build_wan22_stitched_extra_outputs(
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


async def stitch_histories_and_create_history(
    *,
    histories: list[History],
    user_id: int,
    source_task_id: str | None,
    source: str,
    session=None,
) -> Wan22StitchedHistoryResult:
    stitched_video = await stitch_history_videos(histories)
    stitched_task_id = f"wan22_chain_{uuid.uuid4().hex[:24]}"
    output_object_name = f"{user_id}/output_images/{stitched_task_id}.mp4"
    output_file = storage.upload_bytes(
        stitched_video,
        output_object_name,
        content_type="video/mp4",
    )
    if not output_file:
        raise Wan22VideoV2PersistenceError("拼接视频上传失败，请稍后再试")

    stitched_history = _build_stitched_history(
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

    return Wan22StitchedHistoryResult(
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
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
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
