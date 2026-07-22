from __future__ import annotations

import asyncio
import inspect
import logging
import os
from pathlib import Path
import tempfile
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Awaitable, Callable
from uuid import uuid4

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_LTX_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    MODE_WAN22_VIDEO_V2,
)
from src.domain_config.wan22_aio_video import get_wan22_video_v2_cost
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.qqcc_config_service import (
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    get_enabled_qqcc_ai_video_scenes,
    get_enabled_qqcc_video_scenes,
    get_qqcc_ai_video_scene,
    get_qqcc_draw_scene,
    get_qqcc_video_scene,
    has_enabled_qqcc_video_scenes,
    has_enabled_qqcc_ai_video_scenes,
    is_qqcc_main_button_enabled,
)
from src.services.qqcc_draw_chain_service import (
    QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
    calculate_qqcc_draw_chain_cost,
    execute_qqcc_draw_scene_chain,
    resolve_qqcc_draw_chain_prompts,
    resolve_qqcc_draw_scene_chain,
)
from src.services.qqcc_regenerate_metadata import (
    QQCC_REGENERATE_KIND_QUICK_VIDEO,
    build_qqcc_regenerate_result_meta,
)
from src.services.private_qqcc_continuation_service import (
    PrivateQqccContinuationStore,
    StageExecutor,
    build_private_qqcc_draw_continuation_stages,
    create_private_qqcc_continuation,
    execute_private_qqcc_continuation_stage_default,
    persist_private_qqcc_continuation_input,
    resume_private_qqcc_continuation,
)
from src.services.qqcc_runtime_context import is_private_qqcc_bot_context
from src.services.qqcc_scene_billing_service import (
    QqccSceneBillingState,
    RefundCredits,
    refund_qqcc_scene_fixed_charge,
    resolve_qqcc_scene_fixed_credit_cost,
)
from src.services.qqcc_video_frame_adapter import (
    QQCC_VIDEO_ASPECT_SOURCE,
    adapt_qqcc_video_frame_file,
    normalize_qqcc_video_aspect_ratio,
)
from src.services.qqcc_video_scene_chain_service import (
    resolve_qqcc_video_scene_chain,
)
from src.services.qqcc_video_chain_stitch_service import (
    extract_qqcc_video_last_frame,
    persist_and_send_qqcc_video_chain_result,
    stitch_qqcc_video_segments,
)
from src.services.fsm_temp_file_service import FSM_TEMP_DIR
from src.utils import robust_send_message
from src.services.task_service_entrypoints_video import process_video_task_template
from src.services.task_service_entrypoints_specialized import (
    process_ltx_video_task_for_actor,
)
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)

logger = logging.getLogger("services.quick_video_submission")


class QuickVideoSubmissionKind(str, Enum):
    LEGACY_VIDEO = "legacy_video"
    WAN22_VIDEO_V2 = "wan22_video_v2"
    TAIL_FRAME_VIDEO = "tail_frame_video"
    LTX_VIDEO = "ltx_video"
    LTX_TAIL_FRAME_VIDEO = "ltx_tail_frame_video"


class QuickVideoSubmissionRejectReason(str, Enum):
    FEATURE_DISABLED = "feature_disabled"
    INVALID_SETTINGS = "invalid_settings"
    UNSUPPORTED_MODE = "unsupported_mode"


@dataclass(frozen=True)
class QuickVideoSubmissionReject:
    reason: QuickVideoSubmissionRejectReason


@dataclass(frozen=True)
class QqccVideoChainSegment:
    scene_id: str
    scene_kind: str
    kind: QuickVideoSubmissionKind
    mode: str
    resolution: str
    duration: str
    cost: int
    default_prompt_key: str
    default_prompt_text: str
    prompt_override: str | None
    negative_prompt: str
    display_mode_name: str
    result_meta: dict[str, Any]
    lora_name: str = ""
    lora_items: list[dict[str, Any]] = field(default_factory=list)
    tail_draw_chain: list[dict[str, Any]] = field(default_factory=list)
    aspect_ratio: str = QQCC_VIDEO_ASPECT_SOURCE


@dataclass(frozen=True)
class QuickVideoSubmissionPlan:
    kind: QuickVideoSubmissionKind
    mode: str
    resolution: str
    duration: str
    total_cost: int
    default_prompt_key: str
    default_prompt_text: str
    fixed_credit_cost: int | None = None
    billing_id: str = field(default_factory=lambda: uuid4().hex)
    allow_contribute: bool = True
    prompt_override: str | None = None
    negative_prompt: str = ""
    display_mode_name: str | None = None
    result_meta: dict[str, Any] | None = None
    lora_name: str = ""
    lora_items: list[dict[str, Any]] = field(default_factory=list)
    scene_kind: str = "video"
    tail_draw_chain: list[dict[str, Any]] = field(default_factory=list)
    aspect_ratio: str = QQCC_VIDEO_ASPECT_SOURCE
    qqcc_chain_segments: tuple[QqccVideoChainSegment, ...] = ()


@dataclass(frozen=True)
class QuickVideoSettingsReject:
    reason: QuickVideoSubmissionRejectReason


@dataclass(frozen=True)
class QuickVideoSettingsUpdate:
    resolution: str
    duration: str
    alert_key: str | None = None


ProcessVideoTask = Callable[..., Awaitable[Any] | Any]
ProcessGenerationTask = Callable[..., Awaitable[Any] | Any]
ProcessLtxVideoTask = Callable[..., Awaitable[Any] | Any]
ExecuteDrawChain = Callable[..., Awaitable[Any] | Any]
DownloadOutputFile = Callable[..., Awaitable[str] | str]
CleanupTempFiles = Callable[[list[str | None]], None]
AdaptVideoFrameFile = Callable[..., str]
StitchVideoSegments = Callable[[list[bytes]], Awaitable[bytes] | bytes]
ExtractVideoLastFrame = Callable[[bytes], Awaitable[bytes] | bytes]
PersistChainResult = Callable[..., Awaitable[Any] | Any]


QUICK_VIDEO_MODE_CONFIG_KEYS = {
    MODE_PERFECT_VIDEO_INSERT: "missionary",
    MODE_DOGGY_STYLE: "doggy",
    MODE_BLOWJOB: "blowjob",
    MODE_UNDRESS_TONGUE: "undress_tongue",
    MODE_CLOSEUP_BLOWJOB: "closeup_blowjob",
}


_QUICK_VIDEO_MODE_SUBMISSIONS = {
    MODE_PERFECT_VIDEO_INSERT: ("perfect_video_insert", "missionary sex"),
    MODE_DOGGY_STYLE: ("doggy_style", "doggy style sex"),
    MODE_BLOWJOB: ("blowjob", "undress blowjob"),
    MODE_UNDRESS_TONGUE: ("undress_tongue", "undress and show tongue"),
    MODE_CLOSEUP_BLOWJOB: ("closeup_blowjob", "closeup blowjob sex"),
}


def calculate_quick_video_cost(resolution: str, duration: str) -> int:
    return get_wan22_video_v2_cost(resolution, duration)


def normalize_quick_video_selection(
    *,
    resolution: str,
    duration: str,
) -> tuple[str, str]:
    if resolution == "1024p" and duration == "10s":
        return "720p", "10s"
    return resolution, duration


def normalize_qqcc_quick_video_resolution(
    *,
    resolution: str,
    duration: str,
    allowed_resolutions: list[str],
) -> str | None:
    if duration == "10s":
        allowed_resolutions = [res for res in allowed_resolutions if res != "1024p"]
    if not allowed_resolutions:
        return None
    if resolution not in allowed_resolutions:
        return allowed_resolutions[0]
    return resolution


def build_quick_video_settings_update(
    *,
    callback_data: str,
    resolution: str,
    duration: str,
    qqcc_config_present: bool,
    allowed_resolutions: list[str] | None = None,
    allowed_durations: list[str] | None = None,
) -> QuickVideoSettingsUpdate | QuickVideoSettingsReject:
    alert_key: str | None = None
    if callback_data.startswith("set_res_"):
        new_res = callback_data.removeprefix("set_res_")
        if allowed_resolutions is not None and not allowed_resolutions:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.INVALID_SETTINGS
            )
        if allowed_resolutions is not None and new_res not in allowed_resolutions:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.FEATURE_DISABLED
            )
        if new_res == "1024p" and duration == "10s":
            duration = "8s"
            alert_key = "fsm.quick_video.res_dur_conflict"
        resolution = new_res
    elif callback_data.startswith("set_dur_"):
        if qqcc_config_present:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.FEATURE_DISABLED
            )
        new_dur = callback_data.removeprefix("set_dur_")
        if allowed_durations is not None and new_dur not in allowed_durations:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.FEATURE_DISABLED
            )
        if new_dur == "10s" and resolution == "1024p":
            resolution = "720p"
            alert_key = "fsm.quick_video.dur_res_conflict"
        duration = new_dur

    if allowed_resolutions is not None:
        normalized_res = normalize_qqcc_quick_video_resolution(
            resolution=resolution,
            duration=duration,
            allowed_resolutions=allowed_resolutions,
        )
        if normalized_res is None:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.INVALID_SETTINGS
            )
        resolution = normalized_res
    elif allowed_durations is not None:
        normalized_res, normalized_dur = _normalize_allowed_quick_video_settings(
            resolution=resolution,
            duration=duration,
            allowed_resolutions=allowed_resolutions or [],
            allowed_durations=allowed_durations,
        )
        if normalized_res is None or normalized_dur is None:
            return QuickVideoSettingsReject(
                QuickVideoSubmissionRejectReason.INVALID_SETTINGS
            )
        resolution = normalized_res
        duration = normalized_dur

    return QuickVideoSettingsUpdate(
        resolution=resolution,
        duration=duration,
        alert_key=alert_key,
    )


def resolve_quick_video_mode_submission(mode: str) -> tuple[str, str] | None:
    return _QUICK_VIDEO_MODE_SUBMISSIONS.get(mode)


def resolve_qqcc_video_scene_from_fsm_data(
    config: dict[str, Any],
    fsm_data: dict[str, Any],
) -> dict[str, Any] | None:
    scene = get_qqcc_video_scene(config, fsm_data.get("scene_id"))
    if scene is not None:
        return scene
    legacy_scene_id = QUICK_VIDEO_MODE_CONFIG_KEYS.get(fsm_data.get("mode") or "")
    return get_qqcc_video_scene(config, legacy_scene_id)


def resolve_qqcc_ai_video_scene_from_fsm_data(
    config: dict[str, Any],
    fsm_data: dict[str, Any],
) -> dict[str, Any] | None:
    return get_qqcc_ai_video_scene(config, fsm_data.get("scene_id"))


def resolve_qqcc_video_scene_task_type(scene: dict[str, Any]) -> str:
    if scene.get("engine") == VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2:
        return MODE_WAN22_VIDEO_V2
    return (
        MODE_IMAGE_TO_VIDEO
        if str(scene.get("lora_name") or "").strip()
        else MODE_CUSTOM_VIDEO
    )


def _normalize_allowed_quick_video_settings(
    *,
    resolution: str,
    duration: str,
    allowed_resolutions: list[str],
    allowed_durations: list[str],
) -> tuple[str | None, str | None]:
    if not allowed_resolutions or not allowed_durations:
        return None, None

    if resolution not in allowed_resolutions:
        resolution = allowed_resolutions[0]
    if duration not in allowed_durations:
        duration = allowed_durations[0]

    if resolution == "1024p" and duration == "10s":
        if "720p" in allowed_resolutions:
            resolution = "720p"
        elif "8s" in allowed_durations:
            duration = "8s"
        else:
            resolution = allowed_resolutions[0]
            duration = allowed_durations[0]
    return resolution, duration


def _resolve_qqcc_video_end_frame_draw_scene(
    config: dict[str, Any],
    scene: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not scene:
        return None
    draw_scene_id = str(scene.get("end_frame_draw_scene_id") or "").strip()
    return get_qqcc_draw_scene(config, draw_scene_id)


def _build_qqcc_ai_video_chain_segment(
    config: dict[str, Any], scene: dict[str, Any]
) -> QqccVideoChainSegment:
    try:
        duration_seconds = int(scene.get("duration") or 5)
    except (TypeError, ValueError):
        duration_seconds = 5
    if duration_seconds not in {5, 10, 15, 20}:
        duration_seconds = 5
    tail_draw_scene = _resolve_qqcc_video_end_frame_draw_scene(config, scene)
    tail_draw_chain = (
        resolve_qqcc_draw_scene_chain(config, tail_draw_scene)
        if tail_draw_scene is not None
        else []
    )
    prompt = str(scene.get("prompt") or "").strip()
    display_name = str(scene.get("name") or "")
    scene_id = str(scene.get("id") or "").strip()
    return QqccVideoChainSegment(
        scene_id=scene_id,
        scene_kind="ai_video",
        kind=(
            QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO
            if tail_draw_chain
            else QuickVideoSubmissionKind.LTX_VIDEO
        ),
        mode=MODE_LTX_VIDEO,
        resolution="1280x704",
        duration=f"{duration_seconds}s",
        cost=(10 * (duration_seconds // 5))
        + calculate_qqcc_draw_chain_cost(tail_draw_chain),
        default_prompt_key=MODE_LTX_VIDEO,
        default_prompt_text=prompt,
        prompt_override=prompt,
        negative_prompt=str(scene.get("negative_prompt") or "").strip(),
        display_mode_name=display_name,
        result_meta=build_qqcc_regenerate_result_meta(
            kind=QQCC_REGENERATE_KIND_QUICK_VIDEO,
            mode=MODE_LTX_VIDEO,
            scene_id=scene_id,
            scene_kind="ai_video",
            display_mode_name=display_name,
        ),
        lora_items=[
            {"name": item.get("path"), "strength": item.get("strength")}
            for item in (scene.get("lora_items") or [])
            if isinstance(item, dict) and item.get("path")
        ],
        tail_draw_chain=tail_draw_chain,
    )


def _build_qqcc_video_chain_segment(
    config: dict[str, Any],
    scene: dict[str, Any],
    *,
    resolution: str,
) -> QqccVideoChainSegment:
    mode = resolve_qqcc_video_scene_task_type(scene)
    duration = str(scene.get("duration") or "5s")
    tail_draw_scene = _resolve_qqcc_video_end_frame_draw_scene(config, scene)
    tail_draw_chain = (
        resolve_qqcc_draw_scene_chain(config, tail_draw_scene)
        if tail_draw_scene is not None
        else []
    )
    prompt = str(scene.get("prompt") or "").strip()
    display_name = str(scene.get("name") or "")
    scene_id = str(scene.get("id") or "").strip()
    lora_items = [
        {"name": item.get("name"), "strength": item.get("strength")}
        for item in (scene.get("lora_items") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    return QqccVideoChainSegment(
        scene_id=scene_id,
        scene_kind="video",
        kind=(
            QuickVideoSubmissionKind.TAIL_FRAME_VIDEO
            if tail_draw_chain
            else QuickVideoSubmissionKind.WAN22_VIDEO_V2
            if mode == MODE_WAN22_VIDEO_V2
            else QuickVideoSubmissionKind.LEGACY_VIDEO
        ),
        mode=mode,
        resolution=resolution,
        duration=duration,
        cost=calculate_quick_video_cost(resolution, duration)
        + calculate_qqcc_draw_chain_cost(tail_draw_chain),
        default_prompt_key=MODE_CUSTOM_VIDEO,
        default_prompt_text=prompt,
        prompt_override=prompt,
        negative_prompt=str(scene.get("negative_prompt") or "").strip(),
        display_mode_name=display_name,
        result_meta=build_qqcc_regenerate_result_meta(
            kind=QQCC_REGENERATE_KIND_QUICK_VIDEO,
            mode=mode,
            scene_id=scene_id,
            display_mode_name=display_name,
        ),
        lora_name=str(scene.get("lora_name") or ""),
        lora_items=lora_items,
        tail_draw_chain=tail_draw_chain,
        aspect_ratio=normalize_qqcc_video_aspect_ratio(scene.get("aspect_ratio")),
    )


def build_quick_video_submission_plan(
    *,
    fsm_data: dict[str, Any],
    qqcc_config: dict[str, Any] | None,
    allowed_resolutions: list[str] | None,
) -> QuickVideoSubmissionPlan | QuickVideoSubmissionReject:
    resolution, duration = normalize_quick_video_selection(
        resolution=str(fsm_data.get("resolution") or ""),
        duration=str(fsm_data.get("duration") or ""),
    )
    mode = str(fsm_data.get("mode") or "")

    if qqcc_config is None:
        mode_submission = resolve_quick_video_mode_submission(mode)
        if mode_submission is None:
            return QuickVideoSubmissionReject(
                QuickVideoSubmissionRejectReason.UNSUPPORTED_MODE
            )
        default_prompt_key, default_prompt_text = mode_submission
        return QuickVideoSubmissionPlan(
            kind=QuickVideoSubmissionKind.LEGACY_VIDEO,
            mode=mode,
            resolution=resolution,
            duration=duration,
            total_cost=calculate_quick_video_cost(resolution, duration),
            default_prompt_key=default_prompt_key,
            default_prompt_text=default_prompt_text,
        )

    scene_kind = str(fsm_data.get("scene_kind") or "video")
    if scene_kind == "ai_video":
        scene = resolve_qqcc_ai_video_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not is_qqcc_main_button_enabled(qqcc_config, "ai_video")
            or not has_enabled_qqcc_ai_video_scenes(qqcc_config)
            or scene is None
        ):
            return QuickVideoSubmissionReject(
                QuickVideoSubmissionRejectReason.FEATURE_DISABLED
            )
        chain_config = dict(qqcc_config)
        chain_config["ai_video_scenes"] = get_enabled_qqcc_ai_video_scenes(qqcc_config)
        chain_scenes = resolve_qqcc_video_scene_chain(
            chain_config,
            scene_kind="ai_video",
            root_scene_id=str(scene.get("id") or ""),
        )
        chain_segments = tuple(
            _build_qqcc_ai_video_chain_segment(chain_config, chain_scene)
            for chain_scene in chain_scenes
        )
        try:
            duration_seconds = int(scene.get("duration") or 5)
        except (TypeError, ValueError):
            duration_seconds = 5
        if duration_seconds not in {5, 10, 15, 20}:
            duration_seconds = 5
        duration = f"{duration_seconds}s"
        tail_draw_scene = _resolve_qqcc_video_end_frame_draw_scene(qqcc_config, scene)
        tail_draw_chain = (
            resolve_qqcc_draw_scene_chain(qqcc_config, tail_draw_scene)
            if tail_draw_scene is not None
            else []
        )
        prompt = str(scene.get("prompt") or "").strip()
        display_mode_name = str(scene.get("name") or "")
        scene_id = str(scene.get("id") or "").strip()
        fixed_credit_cost = resolve_qqcc_scene_fixed_credit_cost(scene)
        return QuickVideoSubmissionPlan(
            kind=(
                QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO
                if tail_draw_chain
                else QuickVideoSubmissionKind.LTX_VIDEO
            ),
            mode=MODE_LTX_VIDEO,
            resolution="1280x704",
            duration=duration,
            total_cost=(
                fixed_credit_cost
                if fixed_credit_cost is not None
                else sum(segment.cost for segment in chain_segments)
            ),
            default_prompt_key=MODE_LTX_VIDEO,
            default_prompt_text=prompt,
            allow_contribute=False,
            prompt_override=prompt,
            negative_prompt=str(scene.get("negative_prompt") or "").strip(),
            display_mode_name=display_mode_name,
            result_meta=build_qqcc_regenerate_result_meta(
                kind=QQCC_REGENERATE_KIND_QUICK_VIDEO,
                mode=MODE_LTX_VIDEO,
                scene_id=scene_id,
                scene_kind="ai_video",
                display_mode_name=display_mode_name,
            ),
            lora_items=[
                {"name": item.get("path"), "strength": item.get("strength")}
                for item in (scene.get("lora_items") or [])
                if isinstance(item, dict) and item.get("path")
            ],
            tail_draw_chain=tail_draw_chain,
            scene_kind="ai_video",
            qqcc_chain_segments=chain_segments,
            fixed_credit_cost=fixed_credit_cost,
        )

    scene = resolve_qqcc_video_scene_from_fsm_data(qqcc_config, fsm_data)
    if (
        not is_qqcc_main_button_enabled(qqcc_config, "video_edit")
        or not has_enabled_qqcc_video_scenes(qqcc_config)
        or scene is None
    ):
        return QuickVideoSubmissionReject(
            QuickVideoSubmissionRejectReason.FEATURE_DISABLED
        )

    mode = resolve_qqcc_video_scene_task_type(scene)
    duration = str(scene.get("duration") or duration)
    resolution = normalize_qqcc_quick_video_resolution(
        resolution=resolution,
        duration=duration,
        allowed_resolutions=allowed_resolutions or [],
    )
    if resolution is None:
        return QuickVideoSubmissionReject(
            QuickVideoSubmissionRejectReason.INVALID_SETTINGS
        )

    chain_config = dict(qqcc_config)
    chain_config["video_scenes"] = get_enabled_qqcc_video_scenes(qqcc_config)
    chain_scenes = resolve_qqcc_video_scene_chain(
        chain_config,
        scene_kind="video",
        root_scene_id=str(scene.get("id") or ""),
    )
    if (
        len(chain_scenes) > 1
        and resolution == "1024p"
        and any(
            str(chain_scene.get("duration") or "") == "10s"
            for chain_scene in chain_scenes
        )
    ):
        return QuickVideoSubmissionReject(
            QuickVideoSubmissionRejectReason.INVALID_SETTINGS
        )
    chain_segments = tuple(
        _build_qqcc_video_chain_segment(
            chain_config,
            chain_scene,
            resolution=resolution,
        )
        for chain_scene in chain_scenes
    )

    tail_draw_scene = _resolve_qqcc_video_end_frame_draw_scene(qqcc_config, scene)
    tail_draw_chain = (
        resolve_qqcc_draw_scene_chain(qqcc_config, tail_draw_scene)
        if tail_draw_scene is not None
        else []
    )
    prompt = str(scene.get("prompt") or "").strip()
    negative_prompt = str(scene.get("negative_prompt") or "").strip()
    kind = (
        QuickVideoSubmissionKind.TAIL_FRAME_VIDEO
        if tail_draw_chain
        else QuickVideoSubmissionKind.WAN22_VIDEO_V2
        if mode == MODE_WAN22_VIDEO_V2
        else QuickVideoSubmissionKind.LEGACY_VIDEO
    )
    lora_items = [
        {"name": item.get("name"), "strength": item.get("strength")}
        for item in (scene.get("lora_items") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    lora_name = str(scene.get("lora_name") or "")
    scene_id = str(scene.get("id") or "").strip()
    display_mode_name = str(scene.get("name") or "")

    fixed_credit_cost = resolve_qqcc_scene_fixed_credit_cost(scene)
    return QuickVideoSubmissionPlan(
        kind=kind,
        mode=mode,
        resolution=resolution,
        duration=duration,
        total_cost=(
            fixed_credit_cost
            if fixed_credit_cost is not None
            else sum(segment.cost for segment in chain_segments)
        ),
        default_prompt_key=MODE_CUSTOM_VIDEO,
        default_prompt_text=prompt,
        allow_contribute=False,
        prompt_override=prompt,
        negative_prompt=negative_prompt,
        display_mode_name=display_mode_name,
        result_meta=build_qqcc_regenerate_result_meta(
            kind=QQCC_REGENERATE_KIND_QUICK_VIDEO,
            mode=mode,
            scene_id=scene_id,
            display_mode_name=display_mode_name,
        ),
        lora_name=lora_name,
        lora_items=lora_items,
        tail_draw_chain=tail_draw_chain,
        aspect_ratio=normalize_qqcc_video_aspect_ratio(scene.get("aspect_ratio")),
        qqcc_chain_segments=chain_segments,
        fixed_credit_cost=fixed_credit_cost,
    )


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _task_result_has_output(result: Any) -> bool:
    return bool(
        isinstance(result, tuple) and len(result) == 2 and (result[0] or result[1])
    )


def quick_video_plan_requires_continuation(plan: QuickVideoSubmissionPlan) -> bool:
    return len(plan.qqcc_chain_segments) > 1 or plan.kind in {
        QuickVideoSubmissionKind.TAIL_FRAME_VIDEO,
        QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO,
    }


def _serialize_chain_segment(segment: QqccVideoChainSegment) -> dict[str, Any]:
    return {
        "scene_id": segment.scene_id,
        "scene_kind": segment.scene_kind,
        "duration": segment.duration,
        "prompt_override": segment.prompt_override,
        "default_prompt_text": segment.default_prompt_text,
    }


def _build_private_qqcc_video_chain_stages(
    plan: QuickVideoSubmissionPlan,
) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    controls = {
        "base_priority": QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
        "allow_cancel": False,
        "user_cancel_allowed": False,
        "show_queue_status": False,
    }
    segments = plan.qqcc_chain_segments
    for index, segment in enumerate(segments):
        tail_stages: list[dict[str, Any]] = []
        if segment.tail_draw_chain:
            tail_stages = build_private_qqcc_draw_continuation_stages(
                chain=resolve_qqcc_draw_chain_prompts({}, segment.tail_draw_chain),
                final_send_result=False,
                final_allow_contribute=False,
                final_delete_status=False,
            )
            stages.extend(tail_stages)

        is_final = index == len(segments) - 1
        if segment.tail_draw_chain:
            input_mode = "original_current" if index == 0 else "segment_start_current"
        else:
            input_mode = "current"
        common_kwargs: dict[str, Any] = {
            "cleanup": True,
            "send_result": is_final,
            "delete_status": is_final,
            "allow_contribute": False,
            "display_mode_name_override": segment.display_mode_name,
            "result_meta": segment.result_meta,
            **controls,
        }
        if is_final:
            common_kwargs["_qqcc_chain_delivery"] = {
                "mode": plan.mode,
                "resolution": plan.resolution,
                "display_mode_name": plan.display_mode_name,
                "result_meta": plan.result_meta,
                "segments": [_serialize_chain_segment(item) for item in segments],
            }

        if segment.kind in {
            QuickVideoSubmissionKind.LTX_VIDEO,
            QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO,
        }:
            task_kwargs = {
                "prompt": segment.prompt_override or segment.default_prompt_text,
                "resolution": segment.resolution,
                "duration": segment.duration,
                "ltx_mode": "flf2v" if segment.tail_draw_chain else "i2v",
                "lora_items": segment.lora_items,
                **common_kwargs,
            }
            if segment.negative_prompt:
                task_kwargs["negative_prompt"] = segment.negative_prompt
            executor = "ltx_video"
        elif segment.mode == MODE_WAN22_VIDEO_V2:
            task_kwargs = {
                "prompt": segment.prompt_override or segment.default_prompt_text,
                "negative_prompt": segment.negative_prompt,
                "is_video": True,
                "task_type": MODE_WAN22_VIDEO_V2,
                "resolution": segment.resolution,
                "duration": segment.duration,
                "lora_items": segment.lora_items,
                "_qqcc_aspect_ratio": segment.aspect_ratio,
                **common_kwargs,
            }
            executor = "generation"
        else:
            task_kwargs = {
                "mode": segment.mode,
                "default_prompt_key": segment.default_prompt_key,
                "default_prompt_text": segment.default_prompt_text,
                "prompt_override": segment.prompt_override,
                "negative_prompt": segment.negative_prompt,
                "lora_name": segment.lora_name,
                "lora_items": segment.lora_items,
                "use_end_frame": bool(segment.tail_draw_chain),
                "resolution": segment.resolution,
                "duration": segment.duration,
                "_qqcc_aspect_ratio": segment.aspect_ratio,
                **common_kwargs,
            }
            executor = "legacy_video"
        stages.append(
            {
                "executor": executor,
                "input_mode": input_mode,
                "delivery_required": is_final,
                "qqcc_video_segment": True,
                "task_kwargs": task_kwargs,
            }
        )
    return stages


async def run_quick_video_submission_plan(
    *,
    plan: QuickVideoSubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    image_path: str,
    status_msg_id: int | None,
    process_video_task_template_func: ProcessVideoTask = process_video_task_template,
    process_generation_task_func: ProcessGenerationTask = process_generation_task,
    process_ltx_video_task_func: ProcessLtxVideoTask = process_ltx_video_task_for_actor,
    execute_draw_chain_func: ExecuteDrawChain = execute_qqcc_draw_scene_chain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile = download_output_file_to_fsm_temp,
    cleanup_temp_files_func: CleanupTempFiles = cleanup_fsm_temp_files,
    adapt_video_frame_file_func: AdaptVideoFrameFile = adapt_qqcc_video_frame_file,
    private_continuation_store: PrivateQqccContinuationStore | None = None,
    private_continuation_execute_stage_func: StageExecutor | None = None,
    stitch_video_segments_func: StitchVideoSegments = stitch_qqcc_video_segments,
    extract_video_last_frame_func: ExtractVideoLastFrame = extract_qqcc_video_last_frame,
    persist_chain_result_func: PersistChainResult = persist_and_send_qqcc_video_chain_result,
    refund_credits_func: RefundCredits | None = None,
    billing_state: QqccSceneBillingState | None = None,
) -> Any:
    if billing_state is None:
        billing_state = QqccSceneBillingState(
            fixed_credit_cost=plan.fixed_credit_cost,
            billing_id=plan.billing_id,
        )
    if len(plan.qqcc_chain_segments) > 1 and not is_private_qqcc_bot_context(context):
        return await _run_qqcc_video_scene_chain(
            plan=plan,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            image_path=image_path,
            status_msg_id=status_msg_id,
            process_video_task_template_func=process_video_task_template_func,
            process_generation_task_func=process_generation_task_func,
            process_ltx_video_task_func=process_ltx_video_task_func,
            execute_draw_chain_func=execute_draw_chain_func,
            download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
            cleanup_temp_files_func=cleanup_temp_files_func,
            adapt_video_frame_file_func=adapt_video_frame_file_func,
            stitch_video_segments_func=stitch_video_segments_func,
            extract_video_last_frame_func=extract_video_last_frame_func,
            persist_chain_result_func=persist_chain_result_func,
            refund_credits_func=refund_credits_func,
            billing_state=billing_state,
        )
    if plan.aspect_ratio != QQCC_VIDEO_ASPECT_SOURCE:
        source_image_path = image_path
        try:
            image_path = await asyncio.to_thread(
                adapt_video_frame_file_func,
                source_image_path,
                aspect_ratio=plan.aspect_ratio,
            )
        except BaseException:
            cleanup_temp_files_func([source_image_path])
            raise
        if image_path != source_image_path:
            cleanup_temp_files_func([source_image_path])

    if is_private_qqcc_bot_context(context) and len(plan.qqcc_chain_segments) > 1:
        stages = _build_private_qqcc_video_chain_stages(plan)
        try:
            durable_input_ref = await persist_private_qqcc_continuation_input(
                input_ref=image_path,
                telegram_user_id=user_id,
                username=username,
            )
            checkpoint = await create_private_qqcc_continuation(
                stages=stages,
                original_input_ref=durable_input_ref,
                original_input_durable=True,
                context=context,
                chat_id=chat_id,
                telegram_user_id=user_id,
                username=username,
                status_message_id=status_msg_id,
                fixed_credit_cost=plan.fixed_credit_cost,
                store=private_continuation_store,
            )
        finally:
            cleanup_temp_files_func([image_path])

        async def execute_chain_stage(checkpoint_value, stage, ref, runtime_context):
            if private_continuation_execute_stage_func is not None:
                return await private_continuation_execute_stage_func(
                    checkpoint_value, stage, ref, runtime_context
                )
            return await execute_private_qqcc_continuation_stage_default(
                checkpoint_value,
                stage,
                ref,
                runtime_context,
                process_generation_task_func=process_generation_task_func,
                process_video_task_template_func=process_video_task_template_func,
                process_ltx_video_task_func=process_ltx_video_task_func,
                download_video_frame_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
                adapt_video_frame_file_func=adapt_video_frame_file_func,
                cleanup_temp_files_func=cleanup_temp_files_func,
            )

        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=context,
            store=private_continuation_store,
            execute_stage_func=execute_chain_stage,
            refund_credits_func=refund_credits_func,
        )
        return None

    if is_private_qqcc_bot_context(context) and quick_video_plan_requires_continuation(
        plan
    ):
        stages = build_private_qqcc_draw_continuation_stages(
            chain=resolve_qqcc_draw_chain_prompts({}, plan.tail_draw_chain),
            final_send_result=False,
            final_allow_contribute=False,
            final_delete_status=False,
        )
        continuation_controls = {
            "base_priority": QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
            "allow_cancel": False,
            "user_cancel_allowed": False,
            "show_queue_status": False,
        }
        if plan.kind == QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO:
            stages.append(
                {
                    "executor": "ltx_video",
                    "input_mode": "original_current",
                    "delivery_required": True,
                    "task_kwargs": {
                        "prompt": plan.prompt_override or plan.default_prompt_text,
                        "negative_prompt": plan.negative_prompt,
                        "resolution": plan.resolution,
                        "duration": plan.duration,
                        "ltx_mode": "flf2v",
                        "lora_items": plan.lora_items,
                        "cleanup": True,
                        "send_result": True,
                        "delete_status": True,
                        "allow_contribute": False,
                        "display_mode_name_override": plan.display_mode_name,
                        "result_meta": plan.result_meta,
                        **continuation_controls,
                    },
                }
            )
        elif plan.mode == MODE_WAN22_VIDEO_V2:
            stages.append(
                {
                    "executor": "generation",
                    "input_mode": "original_current",
                    "delivery_required": True,
                    "task_kwargs": {
                        "prompt": plan.prompt_override or plan.default_prompt_text,
                        "negative_prompt": plan.negative_prompt,
                        "is_video": True,
                        "task_type": MODE_WAN22_VIDEO_V2,
                        "cleanup": True,
                        "send_result": True,
                        "delete_status": True,
                        "allow_contribute": plan.allow_contribute,
                        "display_mode_name_override": plan.display_mode_name,
                        "result_meta": plan.result_meta,
                        "resolution": plan.resolution,
                        "duration": plan.duration,
                        "lora_items": plan.lora_items,
                        "_qqcc_aspect_ratio": plan.aspect_ratio,
                        **continuation_controls,
                    },
                }
            )
        else:
            stages.append(
                {
                    "executor": "legacy_video",
                    "input_mode": "original_current",
                    "delivery_required": True,
                    "task_kwargs": {
                        "mode": plan.mode,
                        "default_prompt_key": plan.default_prompt_key,
                        "default_prompt_text": plan.default_prompt_text,
                        "prompt_override": plan.prompt_override,
                        "negative_prompt": plan.negative_prompt,
                        "display_mode_name_override": plan.display_mode_name,
                        "result_meta": plan.result_meta,
                        "lora_name": plan.lora_name,
                        "lora_items": plan.lora_items,
                        "use_end_frame": True,
                        "cleanup": True,
                        "send_result": True,
                        "delete_status": True,
                        "allow_contribute": plan.allow_contribute,
                        "resolution": plan.resolution,
                        "duration": plan.duration,
                        "_qqcc_aspect_ratio": plan.aspect_ratio,
                        **continuation_controls,
                    },
                }
            )
        try:
            durable_input_ref = await persist_private_qqcc_continuation_input(
                input_ref=image_path,
                telegram_user_id=user_id,
                username=username,
            )
            checkpoint = await create_private_qqcc_continuation(
                stages=stages,
                original_input_ref=durable_input_ref,
                original_input_durable=True,
                context=context,
                chat_id=chat_id,
                telegram_user_id=user_id,
                username=username,
                status_message_id=status_msg_id,
                fixed_credit_cost=plan.fixed_credit_cost,
                store=private_continuation_store,
            )
        finally:
            cleanup_temp_files_func([image_path])

        async def execute_stage(checkpoint_value, stage, ref, runtime_context):
            if private_continuation_execute_stage_func is not None:
                return await private_continuation_execute_stage_func(
                    checkpoint_value,
                    stage,
                    ref,
                    runtime_context,
                )
            return await execute_private_qqcc_continuation_stage_default(
                checkpoint_value,
                stage,
                ref,
                runtime_context,
                process_generation_task_func=process_generation_task_func,
                process_video_task_template_func=process_video_task_template_func,
                process_ltx_video_task_func=process_ltx_video_task_func,
                download_video_frame_to_fsm_temp_func=(
                    download_output_file_to_fsm_temp_func
                ),
                adapt_video_frame_file_func=adapt_video_frame_file_func,
                cleanup_temp_files_func=cleanup_temp_files_func,
            )

        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=context,
            store=private_continuation_store,
            execute_stage_func=execute_stage,
            refund_credits_func=refund_credits_func,
        )
        return None

    if plan.kind in {
        QuickVideoSubmissionKind.TAIL_FRAME_VIDEO,
        QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO,
    }:
        return await _run_tail_frame_video_plan(
            plan=plan,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            image_path=image_path,
            status_msg_id=status_msg_id,
            process_video_task_template_func=process_video_task_template_func,
            process_generation_task_func=process_generation_task_func,
            process_ltx_video_task_func=process_ltx_video_task_func,
            execute_draw_chain_func=execute_draw_chain_func,
            download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
            cleanup_temp_files_func=cleanup_temp_files_func,
            adapt_video_frame_file_func=adapt_video_frame_file_func,
            refund_credits_func=refund_credits_func,
            billing_state=billing_state,
        )

    if plan.kind == QuickVideoSubmissionKind.LTX_VIDEO:
        optional_negative = (
            {"negative_prompt": plan.negative_prompt} if plan.negative_prompt else {}
        )
        task_kwargs = billing_state.allocate_task_billing()
        result = await _maybe_await(
            process_ltx_video_task_func(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                prompt=plan.prompt_override or plan.default_prompt_text,
                image_path=image_path,
                resolution=plan.resolution,
                duration=plan.duration,
                ltx_mode="i2v",
                lora_items=plan.lora_items or None,
                cleanup=True,
                allow_contribute=False,
                display_mode_name_override=plan.display_mode_name,
                result_meta=plan.result_meta,
                status_msg_id=status_msg_id,
                **optional_negative,
                **task_kwargs,
            )
        )
        if _task_result_has_output(result):
            billing_state.mark_task_succeeded()
        return result

    if plan.kind == QuickVideoSubmissionKind.WAN22_VIDEO_V2:
        result = await _maybe_await(
            process_generation_task_func(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                prompt=plan.prompt_override or plan.default_prompt_text,
                negative_prompt=plan.negative_prompt,
                images=[image_path],
                is_video=True,
                task_type=MODE_WAN22_VIDEO_V2,
                cleanup=True,
                allow_contribute=plan.allow_contribute,
                display_mode_name_override=plan.display_mode_name,
                result_meta=plan.result_meta,
                status_msg_id=status_msg_id,
                resolution=plan.resolution,
                duration=plan.duration,
                lora_items=plan.lora_items or None,
                **billing_state.allocate_task_billing(),
            )
        )
        if _task_result_has_output(result):
            billing_state.mark_task_succeeded()
        return result

    result = await _maybe_await(
        process_video_task_template_func(
            context=context,
            mode=plan.mode,
            default_prompt_key=plan.default_prompt_key,
            default_prompt_text=plan.default_prompt_text,
            prompt_override=plan.prompt_override,
            negative_prompt=plan.negative_prompt,
            display_mode_name_override=plan.display_mode_name,
            result_meta=plan.result_meta,
            lora_name=plan.lora_name,
            lora_items=plan.lora_items or None,
            image_path=image_path,
            cleanup=True,
            allow_contribute=plan.allow_contribute,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            status_msg_id=status_msg_id,
            resolution=plan.resolution,
            duration=plan.duration,
            **billing_state.allocate_task_billing(),
        )
    )
    if _task_result_has_output(result):
        billing_state.mark_task_succeeded()
    return result


async def _run_tail_frame_video_plan(
    *,
    plan: QuickVideoSubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    image_path: str,
    status_msg_id: int | None,
    process_video_task_template_func: ProcessVideoTask,
    process_generation_task_func: ProcessGenerationTask,
    process_ltx_video_task_func: ProcessLtxVideoTask,
    execute_draw_chain_func: ExecuteDrawChain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile,
    cleanup_temp_files_func: CleanupTempFiles,
    adapt_video_frame_file_func: AdaptVideoFrameFile,
    refund_credits_func: RefundCredits | None,
    billing_state: QqccSceneBillingState,
) -> Any:
    end_image_path = None
    video_task_started = False
    try:
        draw_chain = resolve_qqcc_draw_chain_prompts({}, plan.tail_draw_chain)
        chain_result = await _maybe_await(
            execute_draw_chain_func(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                image_path=image_path,
                chain=draw_chain,
                status_msg_id=status_msg_id,
                process_generation_task_func=process_generation_task_func,
                download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
                final_send_result=False,
                final_allow_contribute=False,
                final_delete_status=False,
                keep_initial_image=True,
                download_final_output=True,
                name_hint="qqcc_video_end_frame",
                billing_state=billing_state,
            )
        )
        end_image_path = getattr(chain_result, "local_output_path", None)
        if not end_image_path:
            logger.warning(
                "QQCC video end-frame generation returned no output; video skipped."
            )
            if billing_state.requires_chain_refund:
                await refund_qqcc_scene_fixed_charge(
                    billing_state=billing_state,
                    telegram_user_id=user_id,
                    username=username,
                    **(
                        {"refund_credits_func": refund_credits_func}
                        if refund_credits_func is not None
                        else {}
                    ),
                )
            return None

        if plan.aspect_ratio != QQCC_VIDEO_ASPECT_SOURCE:
            source_end_image_path = end_image_path
            end_image_path = await asyncio.to_thread(
                adapt_video_frame_file_func,
                source_end_image_path,
                aspect_ratio=plan.aspect_ratio,
            )
            if end_image_path != source_end_image_path:
                cleanup_temp_files_func([source_end_image_path])

        video_task_started = True
        if plan.kind == QuickVideoSubmissionKind.LTX_TAIL_FRAME_VIDEO:
            optional_negative = (
                {"negative_prompt": plan.negative_prompt}
                if plan.negative_prompt
                else {}
            )
            result = await _maybe_await(
                process_ltx_video_task_func(
                    context=context,
                    chat_id=chat_id,
                    user_id=user_id,
                    username=username,
                    prompt=plan.prompt_override or plan.default_prompt_text,
                    image_path=image_path,
                    end_image_path=end_image_path,
                    resolution=plan.resolution,
                    duration=plan.duration,
                    ltx_mode="flf2v",
                    lora_items=plan.lora_items or None,
                    cleanup=True,
                    allow_contribute=False,
                    display_mode_name_override=plan.display_mode_name,
                    result_meta=plan.result_meta,
                    status_msg_id=status_msg_id,
                    base_priority=QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
                    allow_cancel=False,
                    user_cancel_allowed=False,
                    show_queue_status=False,
                    **optional_negative,
                    **billing_state.allocate_task_billing(),
                )
            )
            if _task_result_has_output(result):
                billing_state.mark_task_succeeded()
            elif billing_state.requires_chain_refund:
                await refund_qqcc_scene_fixed_charge(
                    billing_state=billing_state,
                    telegram_user_id=user_id,
                    username=username,
                    **(
                        {"refund_credits_func": refund_credits_func}
                        if refund_credits_func is not None
                        else {}
                    ),
                )
            return result
        if plan.mode == MODE_WAN22_VIDEO_V2:
            result = await _maybe_await(
                process_generation_task_func(
                    context=context,
                    chat_id=chat_id,
                    user_id=user_id,
                    username=username,
                    prompt=plan.prompt_override or plan.default_prompt_text,
                    negative_prompt=plan.negative_prompt,
                    images=[image_path, end_image_path],
                    is_video=True,
                    task_type=MODE_WAN22_VIDEO_V2,
                    cleanup=True,
                    allow_contribute=plan.allow_contribute,
                    display_mode_name_override=plan.display_mode_name,
                    result_meta=plan.result_meta,
                    status_msg_id=status_msg_id,
                    resolution=plan.resolution,
                    duration=plan.duration,
                    lora_items=plan.lora_items or None,
                    base_priority=QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
                    allow_cancel=False,
                    user_cancel_allowed=False,
                    show_queue_status=False,
                    **billing_state.allocate_task_billing(),
                )
            )
            if _task_result_has_output(result):
                billing_state.mark_task_succeeded()
            elif billing_state.requires_chain_refund:
                await refund_qqcc_scene_fixed_charge(
                    billing_state=billing_state,
                    telegram_user_id=user_id,
                    username=username,
                    **(
                        {"refund_credits_func": refund_credits_func}
                        if refund_credits_func is not None
                        else {}
                    ),
                )
            return result

        result = await _maybe_await(
            process_video_task_template_func(
                context=context,
                mode=plan.mode,
                default_prompt_key=plan.default_prompt_key,
                default_prompt_text=plan.default_prompt_text,
                prompt_override=plan.prompt_override,
                negative_prompt=plan.negative_prompt,
                display_mode_name_override=plan.display_mode_name,
                result_meta=plan.result_meta,
                lora_name=plan.lora_name,
                lora_items=plan.lora_items or None,
                image_path=image_path,
                end_image_path=end_image_path,
                use_end_frame=True,
                cleanup=True,
                allow_contribute=plan.allow_contribute,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                status_msg_id=status_msg_id,
                resolution=plan.resolution,
                duration=plan.duration,
                base_priority=QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
                allow_cancel=False,
                user_cancel_allowed=False,
                show_queue_status=False,
                **billing_state.allocate_task_billing(),
            )
        )
        if _task_result_has_output(result):
            billing_state.mark_task_succeeded()
        elif billing_state.requires_chain_refund:
            await refund_qqcc_scene_fixed_charge(
                billing_state=billing_state,
                telegram_user_id=user_id,
                username=username,
                **(
                    {"refund_credits_func": refund_credits_func}
                    if refund_credits_func is not None
                    else {}
                ),
            )
        return result
    except BaseException:
        if billing_state.requires_chain_refund:
            await refund_qqcc_scene_fixed_charge(
                billing_state=billing_state,
                telegram_user_id=user_id,
                username=username,
                **(
                    {"refund_credits_func": refund_credits_func}
                    if refund_credits_func is not None
                    else {}
                ),
            )
        raise
    finally:
        if not video_task_started:
            cleanup_temp_files_func([image_path, end_image_path])


def _plan_for_qqcc_chain_segment(
    root_plan: QuickVideoSubmissionPlan,
    segment: QqccVideoChainSegment,
) -> QuickVideoSubmissionPlan:
    return replace(
        root_plan,
        kind=segment.kind,
        mode=segment.mode,
        resolution=segment.resolution,
        duration=segment.duration,
        total_cost=segment.cost,
        default_prompt_key=segment.default_prompt_key,
        default_prompt_text=segment.default_prompt_text,
        prompt_override=segment.prompt_override,
        negative_prompt=segment.negative_prompt,
        display_mode_name=segment.display_mode_name,
        result_meta=segment.result_meta,
        lora_name=segment.lora_name,
        lora_items=segment.lora_items,
        scene_kind=segment.scene_kind,
        tail_draw_chain=segment.tail_draw_chain,
        aspect_ratio=segment.aspect_ratio,
        qqcc_chain_segments=(),
    )


def _write_qqcc_chain_last_frame(frame_bytes: bytes) -> str:
    Path(FSM_TEMP_DIR).mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(
        prefix="qqcc_chain_last_", suffix=".png", dir=FSM_TEMP_DIR
    )
    os.close(fd)
    Path(path).write_bytes(frame_bytes)
    return path


async def _run_qqcc_video_scene_chain(
    *,
    plan: QuickVideoSubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    image_path: str,
    status_msg_id: int | None,
    process_video_task_template_func: ProcessVideoTask,
    process_generation_task_func: ProcessGenerationTask,
    process_ltx_video_task_func: ProcessLtxVideoTask,
    execute_draw_chain_func: ExecuteDrawChain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile,
    cleanup_temp_files_func: CleanupTempFiles,
    adapt_video_frame_file_func: AdaptVideoFrameFile,
    stitch_video_segments_func: StitchVideoSegments,
    extract_video_last_frame_func: ExtractVideoLastFrame,
    persist_chain_result_func: PersistChainResult,
    refund_credits_func: RefundCredits | None,
    billing_state: QqccSceneBillingState,
) -> Any:
    video_segments: list[bytes] = []
    output_files: list[str] = []
    current_image_path = image_path
    failed_index: int | None = None

    for index, segment in enumerate(plan.qqcc_chain_segments):
        segment_plan = _plan_for_qqcc_chain_segment(plan, segment)

        async def call_task(func, kwargs):
            kwargs["send_result"] = False
            kwargs["delete_status"] = False
            kwargs["allow_contribute"] = False
            if index > 0:
                kwargs.update(
                    base_priority=QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
                    allow_cancel=False,
                    user_cancel_allowed=False,
                    show_queue_status=False,
                )
            return await _maybe_await(func(**kwargs))

        async def process_video(**kwargs):
            return await call_task(process_video_task_template_func, kwargs)

        async def process_generation(**kwargs):
            return await call_task(process_generation_task_func, kwargs)

        async def process_ltx(**kwargs):
            return await call_task(process_ltx_video_task_func, kwargs)

        try:
            result = await run_quick_video_submission_plan(
                plan=segment_plan,
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                image_path=current_image_path,
                status_msg_id=status_msg_id,
                process_video_task_template_func=process_video,
                process_generation_task_func=process_generation,
                process_ltx_video_task_func=process_ltx,
                execute_draw_chain_func=execute_draw_chain_func,
                download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
                cleanup_temp_files_func=cleanup_temp_files_func,
                adapt_video_frame_file_func=adapt_video_frame_file_func,
                refund_credits_func=refund_credits_func,
                billing_state=billing_state,
            )
            if not isinstance(result, tuple) or len(result) != 2 or not result[0]:
                raise RuntimeError("QQCC video segment completed without media")
            media_bytes, output_file = result
            video_segments.append(bytes(media_bytes))
            output_files.append(str(output_file or ""))
            if index + 1 < len(plan.qqcc_chain_segments):
                frame_bytes = await _maybe_await(
                    extract_video_last_frame_func(bytes(media_bytes))
                )
                current_image_path = await asyncio.to_thread(
                    _write_qqcc_chain_last_frame, bytes(frame_bytes)
                )
        except Exception:
            failed_index = index
            if not video_segments:
                raise
            logger.exception("QQCC video chain stopped at segment %s", index + 1)
            break

    partial = failed_index is not None
    try:
        stitched = await _maybe_await(stitch_video_segments_func(video_segments))
        persisted = await _maybe_await(
            persist_chain_result_func(
                context=context,
                chat_id=chat_id,
                telegram_user_id=user_id,
                username=username,
                plan=plan,
                video_bytes=stitched,
                segment_output_files=output_files,
                partial=partial,
            )
        )
    except BaseException:
        if billing_state.requires_chain_refund:
            await refund_qqcc_scene_fixed_charge(
                billing_state=billing_state,
                telegram_user_id=user_id,
                username=username,
                **(
                    {"refund_credits_func": refund_credits_func}
                    if refund_credits_func is not None
                    else {}
                ),
            )
        raise
    if partial:
        if billing_state.requires_chain_refund:
            await refund_qqcc_scene_fixed_charge(
                billing_state=billing_state,
                telegram_user_id=user_id,
                username=username,
                **(
                    {"refund_credits_func": refund_credits_func}
                    if refund_credits_func is not None
                    else {}
                ),
            )
        await robust_send_message(
            context.bot,
            chat_id,
            f"第 {failed_index + 1} 段生成失败，已返回前 {len(video_segments)} 段。",
        )
    return persisted
