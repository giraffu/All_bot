from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from enum import StrEnum
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
    calculate_qqcc_draw_chain_cost,
    execute_qqcc_draw_scene_chain,
    resolve_qqcc_draw_chain_prompts,
    resolve_qqcc_draw_scene_chain,
)
from src.services.task_service_entrypoints_video import process_video_task_template
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.wan22_video_v2_extension_service import download_output_file_to_fsm_temp

logger = logging.getLogger("services.quick_video_submission")


class QuickVideoSubmissionKind(StrEnum):
    LEGACY_VIDEO = "legacy_video"
    WAN22_VIDEO_V2 = "wan22_video_v2"
    TAIL_FRAME_VIDEO = "tail_frame_video"


class QuickVideoSubmissionRejectReason(StrEnum):
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
    prompt_override: str | None = None
    display_mode_name: str | None = None
    lora_name: str = ""
    tail_draw_chain: list[dict[str, Any]] = field(default_factory=list)


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
    return MODE_IMAGE_TO_VIDEO if str(scene.get("lora_name") or "").strip() else MODE_CUSTOM_VIDEO


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
    kind = (
        QuickVideoSubmissionKind.TAIL_FRAME_VIDEO
        if tail_draw_chain
        else QuickVideoSubmissionKind.WAN22_VIDEO_V2
        if mode == MODE_WAN22_VIDEO_V2
        else QuickVideoSubmissionKind.LEGACY_VIDEO
    )
    lora_name = "" if mode == MODE_WAN22_VIDEO_V2 else str(scene.get("lora_name") or "")

    return QuickVideoSubmissionPlan(
        kind=kind,
        mode=mode,
        resolution=resolution,
        duration=duration,
        total_cost=calculate_quick_video_cost(resolution, duration)
        + calculate_qqcc_draw_chain_cost(tail_draw_chain),
        default_prompt_key=MODE_CUSTOM_VIDEO,
        default_prompt_text=prompt,
        prompt_override=prompt,
        display_mode_name=str(scene.get("name") or ""),
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
                images=[image_path],
                is_video=True,
                task_type=MODE_WAN22_VIDEO_V2,
                cleanup=True,
                allow_contribute=True,
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
            display_mode_name_override=plan.display_mode_name,
            lora_name=plan.lora_name,
            image_path=image_path,
            cleanup=True,
            allow_contribute=True,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            status_msg_id=status_msg_id,
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
                    images=[image_path, end_image_path],
                    is_video=True,
                    task_type=MODE_WAN22_VIDEO_V2,
                    cleanup=True,
                    allow_contribute=True,
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
                display_mode_name_override=plan.display_mode_name,
                lora_name=plan.lora_name,
                image_path=image_path,
                end_image_path=end_image_path,
                use_end_frame=True,
                cleanup=True,
                allow_contribute=True,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                status_msg_id=status_msg_id,
            )
        )
    finally:
        if not video_task_started:
            cleanup_temp_files_func([image_path, end_image_path])
