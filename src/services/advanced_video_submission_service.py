from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.constants import (
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_WAN22_VIDEO_V2,
)
from src.domain_config.wan22_aio_video import (
    WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS,
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    get_wan22_video_v2_cost,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_resolution_preset,
)
from src.lora_catalog import (
    build_ltx_video_lora_item,
    normalize_ltx_video_lora_items,
)
from src.services.ltx_video_extension_service import (
    build_ltx_full_chain_task_ids,
    normalize_ltx_video_chain_task_ids,
)
from src.services.task_service_entrypoints_specialized import process_ltx_video_task
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task as process_image_to_video_task,
)
from src.services.task_service_generation_wan22 import (
    normalize_wan22_video_v2_chain_task_ids,
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)


class AdvancedVideoSubmissionKind(str, Enum):
    IMAGE_TO_VIDEO = "image_to_video"
    WAN22_VIDEO_V2 = "wan22_video_v2"
    LEGACY_WAN22_IMAGE_TO_VIDEO = "legacy_wan22_image_to_video"
    LTX_VIDEO = "ltx_video"


class AdvancedVideoSubmissionRejectReason(str, Enum):
    MISSING_INPUT = "missing_input"
    DISABLED_MODE = "disabled_mode"
    UNSUPPORTED_MODE = "unsupported_mode"


@dataclass(frozen=True)
class AdvancedVideoSubmissionReject:
    reason: AdvancedVideoSubmissionRejectReason


@dataclass(frozen=True)
class ImageToVideoSubmissionPlan:
    kind: AdvancedVideoSubmissionKind
    task_type: str
    prompt: str
    images: list[str]
    resolution_preset: str
    duration: int
    cost: int
    use_end_frame: bool
    lora_name: str = ""


@dataclass(frozen=True)
class Wan22VideoV2SubmissionPlan:
    kind: AdvancedVideoSubmissionKind
    task_type: str
    prompt: str
    negative_prompt: str
    images: list[str]
    use_end_frame: bool
    resolution_preset: str
    duration: int
    cost: int
    result_meta: dict[str, Any] | None = None
    wan22_prev_task_id: str | None = None
    wan22_chain_task_ids: list[str] = field(default_factory=list)
    lora_name: str | None = None
    lora_strength: float = 1.0


@dataclass(frozen=True)
class LtxVideoSubmissionPlan:
    kind: AdvancedVideoSubmissionKind
    prompt: str
    resolution: str
    duration: str
    cost: int
    ltx_mode: str
    image_path: str | None = None
    end_image_path: str | None = None
    video_path: str | None = None
    ltx_prev_task_id: str | None = None
    ltx_chain_task_ids: list[str] = field(default_factory=list)
    lora_name: str = ""
    lora_strength: float | None = None
    lora_items: list[dict[str, Any]] = field(default_factory=list)


ImageToVideoTask = Callable[..., Any]
Wan22VideoV2Task = Callable[..., Any]
LtxVideoTask = Callable[..., Any]


def build_image_to_video_submission_plan(
    *,
    fsm_data: dict[str, Any],
    conversation_tag: str,
    prompt: str,
) -> ImageToVideoSubmissionPlan | AdvancedVideoSubmissionReject:
    image_path = str(fsm_data.get("image_path") or "").strip()
    if not image_path:
        return AdvancedVideoSubmissionReject(
            AdvancedVideoSubmissionRejectReason.MISSING_INPUT
        )

    end_image_path = str(fsm_data.get("end_image_path") or "").strip()
    use_end_frame = bool(fsm_data.get("use_end_frame") and end_image_path)
    images = [image_path]
    if use_end_frame:
        images.append(end_image_path)

    resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data.get("resolution") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    duration = normalize_wan22_video_v2_duration_seconds(
        fsm_data.get("duration") or WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    )
    task_type = MODE_CUSTOM_VIDEO if conversation_tag == "CUSTOM_VIDEO" else MODE_IMAGE_TO_VIDEO

    return ImageToVideoSubmissionPlan(
        kind=AdvancedVideoSubmissionKind.IMAGE_TO_VIDEO,
        task_type=task_type,
        prompt=prompt,
        images=images,
        resolution_preset=resolution,
        duration=duration,
        cost=get_wan22_video_v2_cost(resolution, duration),
        use_end_frame=use_end_frame,
        lora_name=str(fsm_data.get("lora_name") or ""),
    )


def create_image_to_video_submission_task(
    *,
    plan: ImageToVideoSubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    process_image_to_video_task_func: ImageToVideoTask = process_image_to_video_task,
) -> Any:
    return process_image_to_video_task_func(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=plan.prompt,
        images=plan.images,
        resolution=plan.resolution_preset,
        duration=plan.duration,
        use_end_frame=plan.use_end_frame,
        resolution_preset=plan.resolution_preset,
        task_type=plan.task_type,
        cleanup=True,
        lora_name=plan.lora_name,
    )


def build_wan22_video_v2_submission_plan(
    *,
    data: dict[str, Any],
) -> Wan22VideoV2SubmissionPlan | AdvancedVideoSubmissionReject:
    start_image_path = str(data.get("start_image_path") or "").strip()
    if not start_image_path:
        return AdvancedVideoSubmissionReject(
            AdvancedVideoSubmissionRejectReason.MISSING_INPUT
        )

    end_image_path = str(data.get("end_image_path") or "").strip()
    use_end_frame = bool(data.get("use_end_frame"))
    if use_end_frame and not end_image_path:
        return AdvancedVideoSubmissionReject(
            AdvancedVideoSubmissionRejectReason.MISSING_INPUT
        )

    images = [start_image_path]
    if use_end_frame:
        images.append(end_image_path)

    resolution = normalize_wan22_video_v2_resolution_preset(
        str(data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    duration = normalize_wan22_video_v2_duration_seconds(
        data.get("duration") or WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    )
    extension_task_type = str(data.get("extension_task_type") or MODE_WAN22_VIDEO_V2)
    prompt = str(data.get("prompt") or "").strip()
    negative_prompt = str(data.get("negative_prompt") or "").strip()

    if extension_task_type == MODE_WAN22_VIDEO_V2:
        return Wan22VideoV2SubmissionPlan(
            kind=AdvancedVideoSubmissionKind.WAN22_VIDEO_V2,
            task_type=MODE_WAN22_VIDEO_V2,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=images,
            use_end_frame=use_end_frame,
            resolution_preset=resolution,
            duration=duration,
            cost=get_wan22_video_v2_cost(resolution, duration),
            result_meta=_build_wan22_chain_result_meta(data),
        )

    return Wan22VideoV2SubmissionPlan(
        kind=AdvancedVideoSubmissionKind.LEGACY_WAN22_IMAGE_TO_VIDEO,
        task_type=(
            MODE_IMAGE_TO_VIDEO
            if extension_task_type == MODE_IMAGE_TO_VIDEO
            else MODE_CUSTOM_VIDEO
        ),
        prompt=prompt,
        negative_prompt=negative_prompt,
        images=images,
        use_end_frame=use_end_frame,
        resolution_preset=resolution,
        duration=duration,
        cost=get_wan22_video_v2_cost(resolution, duration),
        wan22_prev_task_id=(
            str(data["extension_prev_task_id"])
            if data.get("extension_prev_task_id")
            else None
        ),
        wan22_chain_task_ids=normalize_wan22_video_v2_chain_task_ids(
            data.get("chain_task_ids")
        ),
        lora_name=str(data.get("lora_name") or "").strip() or None,
        lora_strength=_resolve_legacy_lora_strength(data),
    )


def create_wan22_video_v2_submission_task(
    *,
    plan: Wan22VideoV2SubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    process_wan22_video_v2_task_func: Wan22VideoV2Task = process_wan22_video_v2_task,
    process_image_to_video_task_func: ImageToVideoTask = process_image_to_video_task,
    status_msg_id: int | None = None,
) -> Any:
    if plan.kind == AdvancedVideoSubmissionKind.WAN22_VIDEO_V2:
        kwargs = {}
        if status_msg_id is not None:
            kwargs["status_msg_id"] = status_msg_id
        return process_wan22_video_v2_task_func(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=plan.prompt,
            negative_prompt=plan.negative_prompt,
            images=plan.images,
            use_end_frame=plan.use_end_frame,
            resolution_preset=plan.resolution_preset,
            duration=plan.duration,
            result_meta=plan.result_meta,
            cleanup=True,
            **kwargs,
        )

    kwargs = {}
    if status_msg_id is not None:
        kwargs["status_msg_id"] = status_msg_id
    return process_image_to_video_task_func(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=plan.prompt,
        negative_prompt=plan.negative_prompt,
        images=plan.images,
        use_end_frame=plan.use_end_frame,
        resolution_preset=plan.resolution_preset,
        duration=plan.duration,
        wan22_prev_task_id=plan.wan22_prev_task_id,
        wan22_chain_task_ids=plan.wan22_chain_task_ids,
        task_type=plan.task_type,
        lora_name=plan.lora_name,
        lora_strength=plan.lora_strength,
        cleanup=True,
        **kwargs,
    )


def build_ltx_video_submission_plan(
    *,
    fsm_data: dict[str, Any],
    max_loras: int = 3,
) -> LtxVideoSubmissionPlan | AdvancedVideoSubmissionReject:
    resolution = str(fsm_data.get("resolution") or "1280x704")
    duration = str(fsm_data.get("duration") or "5s")
    ltx_mode = str(fsm_data.get("ltx_mode") or "i2v")
    if ltx_mode == "v2v_audio":
        return AdvancedVideoSubmissionReject(
            AdvancedVideoSubmissionRejectReason.DISABLED_MODE
        )

    image_path = str(fsm_data.get("image_path") or "").strip() or None
    end_image_path = str(fsm_data.get("end_image_path") or "").strip() or None
    video_path = str(fsm_data.get("video_path") or "").strip() or None
    if (
        (ltx_mode == "flf2v" and (not image_path or not end_image_path))
        or (ltx_mode == "i2v" and not image_path)
    ):
        return AdvancedVideoSubmissionReject(
            AdvancedVideoSubmissionRejectReason.MISSING_INPUT
        )

    lora_items = _resolve_ltx_lora_items(fsm_data, max_loras=max_loras)
    first_lora_item = lora_items[0] if lora_items else None
    ltx_prev_task_id = str(fsm_data.get("extension_prev_task_id") or "").strip()
    ltx_chain_task_ids = normalize_ltx_video_chain_task_ids(
        fsm_data.get("chain_task_ids")
    )
    if ltx_prev_task_id and not ltx_chain_task_ids:
        ltx_chain_task_ids = build_ltx_full_chain_task_ids(
            chain_task_ids=[],
            current_task_id=ltx_prev_task_id,
        )

    return LtxVideoSubmissionPlan(
        kind=AdvancedVideoSubmissionKind.LTX_VIDEO,
        prompt=str(fsm_data.get("prompt") or ""),
        resolution=resolution,
        duration=duration,
        cost=_calculate_ltx_cost(resolution, duration),
        ltx_mode=ltx_mode,
        image_path=image_path,
        end_image_path=end_image_path,
        video_path=video_path,
        ltx_prev_task_id=ltx_prev_task_id or None,
        ltx_chain_task_ids=ltx_chain_task_ids,
        lora_name=str(first_lora_item["name"]) if first_lora_item else "",
        lora_strength=float(first_lora_item["strength"]) if first_lora_item else None,
        lora_items=lora_items,
    )


def create_ltx_video_submission_task(
    *,
    plan: LtxVideoSubmissionPlan,
    update: Any,
    context: Any,
    process_ltx_video_task_func: LtxVideoTask = process_ltx_video_task,
) -> Any:
    return process_ltx_video_task_func(
        update=update,
        context=context,
        prompt=plan.prompt,
        image_path=plan.image_path,
        end_image_path=plan.end_image_path,
        video_path=plan.video_path,
        ltx_mode=plan.ltx_mode,
        ltx_prev_task_id=plan.ltx_prev_task_id,
        ltx_chain_task_ids=plan.ltx_chain_task_ids or None,
        lora_name=plan.lora_name,
        lora_strength=plan.lora_strength,
        lora_items=plan.lora_items or None,
        cleanup=True,
    )


def _build_wan22_chain_result_meta(data: dict[str, Any]) -> dict[str, Any] | None:
    if not data.get("extension_prev_task_id"):
        return None
    return {
        "wan22_prev_task_id": str(data["extension_prev_task_id"]),
        "wan22_chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
            data.get("chain_task_ids")
        ),
    }


def _resolve_legacy_lora_strength(data: dict[str, Any]) -> float:
    try:
        return float(data.get("lora_strength"))
    except (TypeError, ValueError):
        return 1.0


def _resolve_ltx_lora_items(
    fsm_data: dict[str, Any],
    *,
    max_loras: int,
) -> list[dict[str, Any]]:
    lora_items = normalize_ltx_video_lora_items(
        fsm_data.get("lora_items"),
        max_items=max_loras,
    )
    if lora_items:
        return lora_items
    fallback_lora_name = str(fsm_data.get("lora_name") or "").strip()
    if not fallback_lora_name:
        return []
    fallback_item = build_ltx_video_lora_item(
        fallback_lora_name,
        strength=fsm_data.get("lora_strength"),
    )
    return [fallback_item] if fallback_item else []


def _calculate_ltx_cost(resolution: str, duration: str) -> int:
    base_cost = LTX_RESOLUTION_COST.get(resolution, 10)
    multiplier = LTX_DURATION_MULTIPLIER.get(duration, 1.0)
    return int(base_cost * multiplier)
