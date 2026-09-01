from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_FLF2V,
    MINIMAX_H3_I2V,
    MINIMAX_H3_REF2V,
    MINIMAX_H3_T2V,
    MiniMaxH3ValidationError,
    build_minimax_h3_spec,
)
from src.services.task_service_generation_image import process_standard_generation_task
from src.services.video_frame_aspect_service import (
    VideoFrameAspectError,
    validate_video_frame_aspects,
)


PRODUCT_NAME = "高级图生视频pro"
MODE_TASK_TYPES = {
    "t2v": MINIMAX_H3_T2V,
    "i2v": MINIMAX_H3_I2V,
    "flf2v": MINIMAX_H3_FLF2V,
    "ref2v": MINIMAX_H3_REF2V,
}


class AdvancedVideoProSubmissionError(ValueError):
    pass


def validate_advanced_video_pro_frame_aspects(
    image_paths: list[str] | tuple[str, ...],
) -> tuple[tuple[int, int], ...]:
    """Validate local first/last frames before quota is checked or deducted."""
    try:
        return validate_video_frame_aspects(image_paths)
    except VideoFrameAspectError as exc:
        raise AdvancedVideoProSubmissionError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class AdvancedVideoProSubmissionPlan:
    mode: str
    task_type: str
    prompt: str
    images: tuple[str, ...]
    reference_descriptions: tuple[str, ...]
    reference_video: str | None
    reference_audio: str | None
    duration: int
    resolution_preset: str
    aspect_ratio: str
    main_model: str
    cost: int
    addon_items: tuple[dict[str, Any], ...]


def build_advanced_video_pro_submission_plan(
    *,
    mode: str,
    prompt: str,
    images: list[str] | tuple[str, ...] = (),
    reference_descriptions: list[str] | tuple[str, ...] = (),
    reference_video: str | None = None,
    reference_audio: str | None = None,
    duration: int | str = 5,
    resolution_preset: str = "preview",
    aspect_ratio: str = "16:9",
    main_model: str = "10eros_bf16",
    addon_model: str | None = None,
    addon_strength: float | None = None,
    addon_items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> AdvancedVideoProSubmissionPlan:
    normalized_mode = str(mode or "").strip().lower()
    task_type = MODE_TASK_TYPES.get(normalized_mode)
    if task_type is None:
        raise AdvancedVideoProSubmissionError("请选择有效的视频生成模式。")
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise AdvancedVideoProSubmissionError("请输入视频提示词。")
    if (
        normalized_mode == "ref2v"
        and reference_video is None
        and not 1 <= len(images) <= 4
    ):
        raise AdvancedVideoProSubmissionError("ref2v 必须提供 1 至 4 张有序参考图。")
    normalized_aspect_ratio = (
        "source" if normalized_mode in {"i2v", "flf2v"} else aspect_ratio
    )
    inputs = {
        "prompt": normalized_prompt,
        "images": list(images),
        "reference_descriptions": list(reference_descriptions),
        "reference_video": reference_video,
        "reference_audio": reference_audio,
        "duration": duration,
        "resolution_preset": resolution_preset,
        "aspect_ratio": normalized_aspect_ratio,
        "main_model": main_model,
        **(
            {"lora_items": list(addon_items)}
            if addon_items is not None
            else {"lora_name": addon_model, "lora_strength": addon_strength}
        ),
    }
    try:
        spec = build_minimax_h3_spec(task_type, inputs)
    except MiniMaxH3ValidationError as exc:
        raise AdvancedVideoProSubmissionError(str(exc)) from exc
    return AdvancedVideoProSubmissionPlan(
        mode=spec.mode,
        task_type=spec.task_type,
        prompt=normalized_prompt,
        images=spec.images,
        reference_descriptions=spec.reference_descriptions,
        reference_video=spec.reference_video,
        reference_audio=spec.reference_audio,
        duration=spec.duration_seconds,
        resolution_preset=spec.resolution_preset,
        aspect_ratio=spec.aspect_ratio,
        main_model=spec.main_model,
        cost=spec.cost,
        addon_items=tuple(
            {"name": item.name, "strength": item.strength} for item in spec.addon_items
        ),
    )


async def submit_advanced_video_pro_plan(
    plan: AdvancedVideoProSubmissionPlan,
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    status_msg_id: int | None = None,
    cleanup: bool = True,
    allow_contribute: bool = False,
    display_mode_name: str = PRODUCT_NAME,
    result_meta: dict[str, Any] | None = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    user_cancel_allowed: bool = True,
    show_queue_status: bool = True,
    cost_override: int | None = None,
    deduct_quota: bool = True,
    process_task_func: Callable[..., Awaitable[Any]] = process_standard_generation_task,
) -> Any:
    persisted_result_meta = {
        **dict(result_meta or {}),
        "minimax_h3_mode": plan.mode,
        "requested_duration": plan.duration,
        "minimax_h3_resolution_preset": plan.resolution_preset,
        "minimax_h3_aspect_ratio": plan.aspect_ratio,
        "minimax_h3_main_model": plan.main_model,
        "lora_items": list(plan.addon_items),
    }
    return await process_task_func(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=plan.prompt,
        images=list(plan.images),
        reference_descriptions=list(plan.reference_descriptions),
        reference_video=plan.reference_video,
        reference_audio=plan.reference_audio,
        is_video=True,
        task_type=plan.task_type,
        duration=plan.duration,
        resolution_preset=plan.resolution_preset,
        aspect_ratio=plan.aspect_ratio,
        main_model=plan.main_model,
        lora_items=list(plan.addon_items) or None,
        status_msg_id=status_msg_id,
        cleanup=cleanup,
        allow_contribute=allow_contribute,
        display_mode_name_override=display_mode_name,
        result_meta=persisted_result_meta,
        base_priority=base_priority,
        allow_cancel=allow_cancel,
        user_cancel_allowed=user_cancel_allowed,
        show_queue_status=show_queue_status,
        cost_override=cost_override,
        deduct_quota=deduct_quota,
    )
