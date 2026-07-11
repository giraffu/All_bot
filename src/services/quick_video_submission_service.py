from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    MODE_WAN22_VIDEO_V2,
)
from src.domain_config.wan22_aio_video import get_wan22_video_v2_cost
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.qqcc_config_service import (
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    get_qqcc_draw_scene,
    get_qqcc_video_scene,
    has_enabled_qqcc_video_scenes,
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
from src.services.task_service_entrypoints_video import process_video_task_template
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


class QuickVideoSubmissionRejectReason(str, Enum):
    FEATURE_DISABLED = "feature_disabled"
    INVALID_SETTINGS = "invalid_settings"
    UNSUPPORTED_MODE = "unsupported_mode"


@dataclass(frozen=True)
class QuickVideoSubmissionReject:
    reason: QuickVideoSubmissionRejectReason


@dataclass(frozen=True)
class QuickVideoSubmissionPlan:
    kind: QuickVideoSubmissionKind
    mode: str
    resolution: str
    duration: str
    total_cost: int
    default_prompt_key: str
    default_prompt_text: str
    allow_contribute: bool = True
    prompt_override: str | None = None
    negative_prompt: str = ""
    display_mode_name: str | None = None
    result_meta: dict[str, Any] | None = None
    lora_name: str = ""
    tail_draw_chain: list[dict[str, Any]] = field(default_factory=list)


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
ExecuteDrawChain = Callable[..., Awaitable[Any] | Any]
DownloadOutputFile = Callable[..., Awaitable[str] | str]
CleanupTempFiles = Callable[[list[str | None]], None]


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
    lora_name = "" if mode == MODE_WAN22_VIDEO_V2 else str(scene.get("lora_name") or "")
    scene_id = str(scene.get("id") or "").strip()
    display_mode_name = str(scene.get("name") or "")

    return QuickVideoSubmissionPlan(
        kind=kind,
        mode=mode,
        resolution=resolution,
        duration=duration,
        total_cost=calculate_quick_video_cost(resolution, duration)
        + calculate_qqcc_draw_chain_cost(tail_draw_chain),
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
        tail_draw_chain=tail_draw_chain,
    )


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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
    execute_draw_chain_func: ExecuteDrawChain = execute_qqcc_draw_scene_chain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile = download_output_file_to_fsm_temp,
    cleanup_temp_files_func: CleanupTempFiles = cleanup_fsm_temp_files,
) -> None:
    if plan.kind == QuickVideoSubmissionKind.TAIL_FRAME_VIDEO:
        await _run_tail_frame_video_plan(
            plan=plan,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            image_path=image_path,
            status_msg_id=status_msg_id,
            process_video_task_template_func=process_video_task_template_func,
            process_generation_task_func=process_generation_task_func,
            execute_draw_chain_func=execute_draw_chain_func,
            download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
            cleanup_temp_files_func=cleanup_temp_files_func,
        )
        return

    if plan.kind == QuickVideoSubmissionKind.WAN22_VIDEO_V2:
        await _maybe_await(
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
            )
        )
        return

    await _maybe_await(
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
            image_path=image_path,
            cleanup=True,
            allow_contribute=plan.allow_contribute,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            status_msg_id=status_msg_id,
            resolution=plan.resolution,
            duration=plan.duration,
        )
    )


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
    execute_draw_chain_func: ExecuteDrawChain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile,
    cleanup_temp_files_func: CleanupTempFiles,
) -> None:
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
            )
        )
        end_image_path = getattr(chain_result, "local_output_path", None)
        if not end_image_path:
            logger.warning(
                "QQCC video end-frame generation returned no output; video skipped."
            )
            return

        video_task_started = True
        if plan.mode == MODE_WAN22_VIDEO_V2:
            await _maybe_await(
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
                    base_priority=QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
                    allow_cancel=False,
                    user_cancel_allowed=False,
                )
            )
            return

        await _maybe_await(
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
            )
        )
    finally:
        if not video_task_started:
            cleanup_temp_files_func([image_path, end_image_path])
