from __future__ import annotations

import inspect
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable
from uuid import uuid4

from src.constants import (
    MODE_EDIT,
    MODE_I2I_DRAW,
    MODE_IMG2IMG_LORA,
    MODE_MASTURBATION,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
    MODE_UNDRESS,
    TASK_COSTS,
)
from src.lora_catalog import get_lora_default_strength
from src.services.qqcc_config_service import (
    get_qqcc_draw_scene,
    get_qqcc_filter_scene,
    has_enabled_qqcc_draw_scenes,
    has_enabled_qqcc_filter_scenes,
    is_qqcc_main_button_enabled,
    resolve_qqcc_prompt,
)
from src.services.qqcc_draw_chain_service import (
    QQCC_SCENE_KIND_DRAW,
    QQCC_SCENE_KIND_FILTER,
    calculate_qqcc_draw_chain_cost,
    execute_qqcc_draw_scene_chain,
    is_qqcc_original_face_swap_enabled,
    resolve_qqcc_draw_chain_prompts,
    resolve_qqcc_draw_scene_chain,
    resolve_qqcc_draw_scene_task_type,
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
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.qqcc_regenerate_metadata import (
    QQCC_REGENERATE_KIND_QUICK_IMAGE,
    build_qqcc_regenerate_result_meta,
)
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.qqcc_runtime_context import is_private_qqcc_bot_context
from src.services.qqcc_scene_billing_service import (
    QqccSceneBillingState,
    RefundCredits,
    refund_qqcc_scene_fixed_charge,
    resolve_qqcc_scene_fixed_credit_cost,
)
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)


class QuickImageSubmissionKind(str, Enum):
    SINGLE_IMAGE = "single_image"
    RANDOM_FACESWAP = "random_faceswap"
    DRAW_CHAIN = "draw_chain"


class QuickImageSubmissionRejectReason(str, Enum):
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
    fixed_credit_cost: int | None = None
    billing_id: str = field(default_factory=lambda: uuid4().hex)
    allow_contribute: bool = True
    prompt: str = ""
    images: list[str] = field(default_factory=list)
    draw_chain: list[dict[str, Any]] = field(default_factory=list)
    lora_name: str = ""
    lora_strength: float | None = None
    cleanup: bool = True
    preserve_input_for_again: bool = False
    reply_markup: Any = None
    display_mode_name: str | None = None
    result_meta: dict[str, Any] | None = None


ProcessGenerationTask = Callable[..., Awaitable[Any] | Any]
ExecuteDrawChain = Callable[..., Awaitable[Any] | Any]
DownloadOutputFile = Callable[..., Awaitable[str] | str]
RandomChoice = Callable[[list[str]], str]
ListObjects = Callable[..., Iterable[str]]


QQCC_AI_DRAW_TASK_TYPES = (
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
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


def is_qqcc_quick_filter_mode_enabled(config: dict[str, Any], mode: str) -> bool:
    return (
        mode in QQCC_AI_DRAW_TASK_TYPES
        and is_qqcc_main_button_enabled(config, "ai_filter")
        and has_enabled_qqcc_filter_scenes(config)
    )


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


def quick_image_plan_requires_continuation(plan: QuickImageSubmissionPlan) -> bool:
    if plan.kind != QuickImageSubmissionKind.DRAW_CHAIN:
        return False
    subtask_count = len(plan.draw_chain) + sum(
        1 for scene in plan.draw_chain if is_qqcc_original_face_swap_enabled(scene)
    )
    return subtask_count > 1


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
    private_continuation_store: PrivateQqccContinuationStore | None = None,
    private_continuation_execute_stage_func: StageExecutor | None = None,
    refund_credits_func: RefundCredits | None = None,
) -> None:
    billing_state = QqccSceneBillingState(
        fixed_credit_cost=plan.fixed_credit_cost,
        billing_id=plan.billing_id,
    )
    if is_private_qqcc_bot_context(context) and quick_image_plan_requires_continuation(
        plan
    ):
        stages = build_private_qqcc_draw_continuation_stages(
            chain=plan.draw_chain,
            final_send_result=True,
            final_allow_contribute=plan.allow_contribute,
            final_delete_status=True,
            final_display_mode_name=plan.display_mode_name,
            final_result_meta=plan.result_meta,
        )
        local_input_ref = _require_first_image(plan)
        try:
            durable_input_ref = await persist_private_qqcc_continuation_input(
                input_ref=local_input_ref,
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
            cleanup_fsm_temp_files([local_input_ref])

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
            )

        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=context,
            store=private_continuation_store,
            execute_stage_func=execute_stage,
            refund_credits_func=refund_credits_func,
        )
        return

    if plan.kind == QuickImageSubmissionKind.DRAW_CHAIN:
        try:
            result = await _maybe_await(
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
                    final_allow_contribute=plan.allow_contribute,
                    final_delete_status=True,
                    final_display_mode_name=plan.display_mode_name,
                    final_result_meta=plan.result_meta,
                    billing_state=billing_state,
                )
            )
            if (
                plan.fixed_credit_cost is not None
                and billing_state.requires_chain_refund
                and not getattr(result, "output_file", None)
            ):
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
        "allow_contribute": plan.allow_contribute,
    }
    if plan.display_mode_name:
        task_kwargs["display_mode_name_override"] = plan.display_mode_name
    if plan.result_meta is not None:
        task_kwargs["result_meta"] = plan.result_meta
    if plan.reply_markup is not None:
        task_kwargs["reply_markup"] = plan.reply_markup
    if plan.lora_name:
        task_kwargs["lora_name"] = plan.lora_name
        task_kwargs["lora_strength"] = plan.lora_strength
    task_kwargs.update(billing_state.allocate_task_billing())

    result = await _maybe_await(process_generation_task_func(**task_kwargs))
    if isinstance(result, tuple) and len(result) == 2 and result[1]:
        billing_state.mark_task_succeeded()


def _build_qqcc_draw_chain_plan(
    *,
    fsm_data: dict[str, Any],
    qqcc_config: dict[str, Any],
    image_path: str | None,
) -> QuickImageSubmissionPlan | QuickImageSubmissionReject:
    scene_kind = str(fsm_data.get("scene_kind") or QQCC_SCENE_KIND_DRAW).strip()
    if scene_kind == QQCC_SCENE_KIND_FILTER:
        scene = get_qqcc_filter_scene(qqcc_config, fsm_data.get("scene_id"))
    else:
        scene_kind = QQCC_SCENE_KIND_DRAW
        scene = get_qqcc_draw_scene(qqcc_config, fsm_data.get("scene_id"))
    if scene is None:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    draw_chain = resolve_qqcc_draw_scene_chain(
        qqcc_config,
        scene,
        scene_kind=scene_kind,
    )
    if not draw_chain:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    mode = resolve_qqcc_draw_scene_task_type(draw_chain[0])
    if scene_kind == QQCC_SCENE_KIND_FILTER:
        enabled = is_qqcc_quick_filter_mode_enabled(qqcc_config, mode)
    else:
        enabled = is_qqcc_quick_image_mode_enabled(qqcc_config, mode)
    if not enabled:
        return QuickImageSubmissionReject(
            QuickImageSubmissionRejectReason.FEATURE_DISABLED
        )

    draw_chain = resolve_qqcc_draw_chain_prompts(qqcc_config, draw_chain)
    images = [image_path] if image_path else []
    scene_id = str(scene.get("id") or "").strip()
    display_mode_name = str(scene.get("name") or "").strip()
    fixed_credit_cost = resolve_qqcc_scene_fixed_credit_cost(scene)
    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.DRAW_CHAIN,
        mode=mode,
        task_type=mode,
        total_cost=(
            fixed_credit_cost
            if fixed_credit_cost is not None
            else calculate_qqcc_draw_chain_cost(draw_chain)
        ),
        fixed_credit_cost=fixed_credit_cost,
        allow_contribute=False,
        prompt=str(draw_chain[0].get("prompt") or ""),
        images=images,
        draw_chain=draw_chain,
        display_mode_name=display_mode_name or None,
        result_meta=build_qqcc_regenerate_result_meta(
            kind=QQCC_REGENERATE_KIND_QUICK_IMAGE,
            mode=mode,
            scene_id=scene_id,
            scene_kind=scene_kind,
            display_mode_name=display_mode_name,
        ),
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

    is_qqcc = qqcc_config is not None
    display_mode_name = "快速换脸" if is_qqcc else None
    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.RANDOM_FACESWAP,
        mode=mode,
        task_type="face_swap",
        total_cost=total_cost,
        allow_contribute=not is_qqcc,
        prompt=prompt,
        images=images,
        cleanup=False,
        preserve_input_for_again=True,
        reply_markup=reply_markup,
        display_mode_name=display_mode_name,
        result_meta=(
            build_qqcc_regenerate_result_meta(
                kind=QQCC_REGENERATE_KIND_QUICK_IMAGE,
                mode=mode,
                display_mode_name=display_mode_name or "",
            )
            if is_qqcc
            else None
        ),
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
    lora_name = (
        str(fsm_data.get("lora_name") or "") if mode == MODE_IMG2IMG_LORA else ""
    )
    return QuickImageSubmissionPlan(
        kind=QuickImageSubmissionKind.SINGLE_IMAGE,
        mode=mode,
        task_type=mode,
        total_cost=total_cost,
        allow_contribute=qqcc_config is None,
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
