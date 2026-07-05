from __future__ import annotations

import inspect
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable, Iterable

from src.constants import (
    MODE_EDIT,
    MODE_I2I_DRAW,
    MODE_IMG2IMG_LORA,
    MODE_MASTURBATION,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
    MODE_UNDRESS,
    TASK_COSTS,
)
from src.lora_catalog import get_lora_default_strength
from src.services.qqcc_config_service import (
    get_qqcc_draw_scene,
    has_enabled_qqcc_draw_scenes,
    is_qqcc_main_button_enabled,
    resolve_qqcc_prompt,
)
from src.services.qqcc_draw_chain_service import (
    calculate_qqcc_draw_chain_cost,
    execute_qqcc_draw_scene_chain,
    resolve_qqcc_draw_chain_prompts,
    resolve_qqcc_draw_scene_chain,
    resolve_qqcc_draw_scene_task_type,
)
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)


class QuickImageSubmissionKind(StrEnum):
    SINGLE_IMAGE = "single_image"
    RANDOM_FACESWAP = "random_faceswap"
    DRAW_CHAIN = "draw_chain"


class QuickImageSubmissionRejectReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    NO_TEMPLATE = "no_template"
    UNSUPPORTED_MODE = "unsupported_mode"


@dataclass(frozen=True)
class QuickImageSubmissionReject:
    reason: QuickImageSubmissionRejectReason


@dataclass(frozen=True)
class QuickImageSubmissionPlan:
    kind: QuickImageSubmissionKind
    mode: str
    task_type: str
    total_cost: int
    prompt: str = ""
    images: list[str] = field(default_factory=list)
    draw_chain: list[dict[str, Any]] = field(default_factory=list)
    lora_name: str = ""
    lora_strength: float | None = None
    cleanup: bool = True
    preserve_input_for_again: bool = False
    reply_markup: Any = None


ProcessGenerationTask = Callable[..., Awaitable[Any] | Any]
ExecuteDrawChain = Callable[..., Awaitable[Any] | Any]
DownloadOutputFile = Callable[..., Awaitable[str] | str]
RandomChoice = Callable[[list[str]], str]
ListObjects = Callable[..., Iterable[str]]


QQCC_AI_DRAW_TASK_TYPES = (
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
DEFAULT_I2I_DRAW_UNDRESS_PROMPT = (
    "全身广角镜头，保持面部五官、脸型、发型、表情和肤色不变，"
    "保持身体姿势不变。将衣服自然移除，生成真实皮肤质感和完整身体，"
    "不要改变人物身份，不要裁剪头部。"
)
_QUICK_IMAGE_SUPPORTED_MODES = {
    MODE_UNDRESS,
    MODE_MASTURBATION,
    MODE_RANDOM_FACESWAP,
    MODE_I2I_DRAW,
    *QQCC_AI_DRAW_TASK_TYPES,
}
_IMAGE_TEMPLATE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def is_qqcc_quick_image_mode_enabled(config: dict[str, Any], mode: str) -> bool:
    if mode == MODE_UNDRESS:
        return False
    if mode == MODE_I2I_DRAW:
        return False
    if mode == MODE_MASTURBATION:
        return False
    if mode == MODE_RANDOM_FACESWAP:
        return is_qqcc_main_button_enabled(config, "quick_faceswap")
    if mode in QQCC_AI_DRAW_TASK_TYPES:
        return is_qqcc_main_button_enabled(
            config, "ai_draw"
        ) and has_enabled_qqcc_draw_scenes(config)
    return False


def list_quick_faceswap_template_files(
    *,
    list_objects_func: ListObjects | None = None,
    bucket: str | None = None,
) -> list[str]:
    if list_objects_func is None:
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage

        list_objects_func = storage.list_objects
        bucket = bucket or MINIO_TEMPLATE_BUCKET
    return _filter_template_files(list_objects_func("quick_face/", bucket=bucket))


def build_quick_image_submission_plan(
    *,
    fsm_data: dict[str, Any],
    qqcc_config: dict[str, Any] | None,
    image_path: str | None = None,
    prompts_config: dict[str, str] | None = None,
    template_files: Iterable[str] | None = None,
    random_choice_func: RandomChoice = random.choice,
    reply_markup: Any = None,
) -> QuickImageSubmissionPlan | QuickImageSubmissionReject:
    mode = str(fsm_data.get("mode") or "")
    if mode not in _QUICK_IMAGE_SUPPORTED_MODES:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.UNSUPPORTED_MODE
        )

    if qqcc_config is not None and mode in QQCC_AI_DRAW_TASK_TYPES:
        return _build_qqcc_draw_chain_plan(
            fsm_data=fsm_data,
            qqcc_config=qqcc_config,
            image_path=image_path,
        )

    if qqcc_config is not None and not is_qqcc_quick_image_mode_enabled(
        qqcc_config, mode
    ):
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    total_cost = _resolve_total_cost(fsm_data, mode)
    if mode == MODE_RANDOM_FACESWAP:
        return _build_random_faceswap_plan(
            mode=mode,
            total_cost=total_cost,
            image_path=image_path,
            prompts_config=prompts_config,
            qqcc_config=qqcc_config,
            template_files=template_files,
            random_choice_func=random_choice_func,
            reply_markup=reply_markup,
        )

    return _build_single_image_plan(
        mode=mode,
        total_cost=total_cost,
        image_path=image_path,
        prompts_config=prompts_config,
        qqcc_config=qqcc_config,
        fsm_data=fsm_data,
    )


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def run_quick_image_submission_plan(
    *,
    plan: QuickImageSubmissionPlan,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    status_msg_id: int | None,
    process_generation_task_func: ProcessGenerationTask = process_generation_task,
    execute_draw_chain_func: ExecuteDrawChain = execute_qqcc_draw_scene_chain,
    download_output_file_to_fsm_temp_func: DownloadOutputFile = download_output_file_to_fsm_temp,
) -> None:
    if plan.kind == QuickImageSubmissionKind.DRAW_CHAIN:
        await _maybe_await(
            execute_draw_chain_func(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                image_path=_require_first_image(plan),
                chain=plan.draw_chain,
                status_msg_id=status_msg_id,
                process_generation_task_func=process_generation_task_func,
                download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp_func,
                final_send_result=True,
                final_allow_contribute=True,
                final_delete_status=True,
            )
        )
        return

    task_kwargs: dict[str, Any] = {
        "context": context,
        "chat_id": chat_id,
        "user_id": user_id,
        "username": username,
        "prompt": plan.prompt,
        "images": plan.images,
        "task_type": plan.task_type,
        "cleanup": plan.cleanup,
    }
    if plan.reply_markup is not None:
        task_kwargs["reply_markup"] = plan.reply_markup
    if plan.lora_name:
        task_kwargs["lora_name"] = plan.lora_name
        task_kwargs["lora_strength"] = plan.lora_strength

    await _maybe_await(process_generation_task_func(**task_kwargs))


def _build_qqcc_draw_chain_plan(
    *,
    fsm_data: dict[str, Any],
    qqcc_config: dict[str, Any],
    image_path: str | None,
) -> QuickImageSubmissionPlan | QuickImageSubmissionReject:
    scene = get_qqcc_draw_scene(qqcc_config, fsm_data.get("scene_id"))
    if scene is None:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    draw_chain = resolve_qqcc_draw_scene_chain(qqcc_config, scene)
    if not draw_chain:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    mode = resolve_qqcc_draw_scene_task_type(draw_chain[0])
    if not is_qqcc_quick_image_mode_enabled(qqcc_config, mode):
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    draw_chain = resolve_qqcc_draw_chain_prompts(qqcc_config, draw_chain)
    images = [image_path] if image_path else []
    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.DRAW_CHAIN,
        mode=mode,
        task_type=mode,
        total_cost=calculate_qqcc_draw_chain_cost(draw_chain),
        prompt=str(draw_chain[0].get("prompt") or ""),
        images=images,
        draw_chain=draw_chain,
    )


def _build_random_faceswap_plan(
    *,
    mode: str,
    total_cost: int,
    image_path: str | None,
    prompts_config: dict[str, str] | None,
    qqcc_config: dict[str, Any] | None,
    template_files: Iterable[str] | None,
    random_choice_func: RandomChoice,
    reply_markup: Any,
) -> QuickImageSubmissionPlan | QuickImageSubmissionReject:
    prompts_config = prompts_config or {}
    prompt = (
        resolve_qqcc_prompt(qqcc_config, "face_swap", prompts_config, "face swap")
        if qqcc_config is not None
        else prompts_config.get("face_swap", "face swap")
    )

    images: list[str] = []
    if image_path and template_files is not None:
        filtered_templates = _filter_template_files(template_files)
        if not filtered_templates:
            return QuickImageSubmissionReject(
                QuickImageSubmissionRejectReason.NO_TEMPLATE
            )
        images = [f"template:{random_choice_func(filtered_templates)}", image_path]
    elif image_path:
        images = [image_path]

    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.RANDOM_FACESWAP,
        mode=mode,
        task_type="face_swap",
        total_cost=total_cost,
        prompt=prompt,
        images=images,
        cleanup=False,
        preserve_input_for_again=True,
        reply_markup=reply_markup,
    )


def _build_single_image_plan(
    *,
    mode: str,
    total_cost: int,
    image_path: str | None,
    prompts_config: dict[str, str] | None,
    qqcc_config: dict[str, Any] | None,
    fsm_data: dict[str, Any],
) -> QuickImageSubmissionPlan:
    prompts_config = prompts_config or {}
    prompt = _resolve_single_image_prompt(
        mode=mode,
        prompts_config=prompts_config,
        qqcc_config=qqcc_config,
        fsm_data=fsm_data,
    )
    lora_name = str(fsm_data.get("lora_name") or "") if mode == MODE_IMG2IMG_LORA else ""
    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.SINGLE_IMAGE,
        mode=mode,
        task_type=mode,
        total_cost=total_cost,
        prompt=prompt,
        images=[image_path] if image_path else [],
        lora_name=lora_name,
        lora_strength=get_lora_default_strength(lora_name) if lora_name else None,
    )


def _resolve_single_image_prompt(
    *,
    mode: str,
    prompts_config: dict[str, str],
    qqcc_config: dict[str, Any] | None,
    fsm_data: dict[str, Any],
) -> str:
    if mode in QQCC_AI_DRAW_TASK_TYPES:
        prompt = str(fsm_data.get("prompt_override") or "").strip()
        return prompt or mode
    if mode == MODE_I2I_DRAW:
        prompt_key = "i2i_draw_quick_undress"
        fallback_prompt = DEFAULT_I2I_DRAW_UNDRESS_PROMPT
    else:
        prompt_key = mode
        fallback_prompt = mode

    if qqcc_config is not None:
        return resolve_qqcc_prompt(
            qqcc_config,
            prompt_key,
            prompts_config,
            fallback_prompt,
        )
    return prompts_config.get(prompt_key, fallback_prompt)


def _resolve_total_cost(fsm_data: dict[str, Any], mode: str) -> int:
    try:
        return int(fsm_data.get("cost") or TASK_COSTS.get(mode, 2))
    except (TypeError, ValueError):
        return TASK_COSTS.get(mode, 2)


def _filter_template_files(template_files: Iterable[str]) -> list[str]:
    return [
        template_file
        for template_file in template_files
        if str(template_file).lower().endswith(_IMAGE_TEMPLATE_EXTENSIONS)
    ]


def _require_first_image(plan: QuickImageSubmissionPlan) -> str:
    if not plan.images:
        raise ValueError("Quick image submission plan has no input image")
    return plan.images[0]
