from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.handlers.fsm.fsm_shared import translate_fsm_text
from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_draw_scene_callback_data,
    build_quick_draw_v1_scene_callback_data,
)
from src.handlers.fsm.quick_video_callback_data import (
    build_quick_ref2v_template_callback_data,
)
from src.services.qqcc_config_service import (
    get_qqcc_copywriting_override,
    get_qqcc_draw_scene,
    get_qqcc_draw_scene_v1,
    is_qqcc_main_button_enabled,
    render_qqcc_copywriting,
)
from src.services.qqcc_runtime_context import (
    get_private_qqcc_bot_id,
    is_qqcc_bot_context,
)
from src.services.quick_video_entry_service import QuickVideoEntryPlan
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionReject,
    build_quick_video_submission_plan,
)


logger = logging.getLogger("fsm.quick_video.entry_view")
_t = translate_fsm_text


def build_ref2v_template_markup(scene: dict[str, Any]) -> InlineKeyboardMarkup:
    reference_names = list(scene.get("reference_image_names") or [])
    reference_images = list(scene.get("reference_images") or [])
    buttons = [
        InlineKeyboardButton(
            f"替换：{reference_names[index] or f'模板 {index + 1}'}",
            callback_data=build_quick_ref2v_template_callback_data(
                str(scene["id"]), index
            ),
        )
        for index in range(len(reference_images))
    ]
    return InlineKeyboardMarkup(
        [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    )


def build_ref2v_scene_prompt(
    *,
    scene: dict[str, Any],
    selected_name: str,
    cost_text: str | None = None,
    replacement_confirmed: bool = False,
) -> str:
    scene_name = str(scene.get("name") or "AI视频")
    if replacement_confirmed:
        status = f"✅ 已使用你发送的图片替换【{selected_name}】模板。"
        action = "现在请发送女性人物图片（正面、脸部清晰），我会使用当前模板生成视频。"
        replacement_tip = (
            "其他模板仍然保留；如需继续替换，可点击下方对应的“替换：模板名称”按钮。"
        )
    else:
        status = f"✅ 当前默认模板【{selected_name}】。"
        action = (
            "你可以直接发送女性人物图片（正面、脸部清晰），我会使用当前模板生成视频。"
        )
        replacement_tip = (
            "如需更换参考模板，点击下方“替换：模板名称”按钮，然后发送新的模板图片。"
        )
    prompt = (
        f"🎞️ {'已更新' if replacement_confirmed else '已切换到'}【{scene_name}】场景。\n\n"
        f"{status}\n\n"
        f"{action}\n\n"
        f"{replacement_tip}"
        "模板替换完成后，我会再次提示你发送女性人物图片。\n\n"
        "随时可以发送 /cancel 退出流程。"
    )
    return f"{prompt}\n\n{cost_text}" if cost_text else prompt


def resolve_qqcc_scene_display_cost(
    *, fsm_data: dict[str, Any], qqcc_config: dict[str, Any]
) -> int | None:
    plan = build_quick_video_submission_plan(
        fsm_data=fsm_data,
        qqcc_config=qqcc_config,
        allowed_resolutions=None,
    )
    if isinstance(plan, QuickVideoSubmissionReject):
        logger.warning(
            "Unable to resolve QQCC scene display cost scene=%s reason=%s",
            fsm_data.get("scene_id"),
            plan.reason,
        )
        return None
    return plan.total_cost


def _append_draw_jump_button(
    *,
    reply_markup: InlineKeyboardMarkup | None,
    scene: dict[str, Any],
    plan: QuickVideoEntryPlan,
) -> InlineKeyboardMarkup | None:
    qqcc_config = plan.qqcc_config
    if qqcc_config is None:
        return reply_markup
    is_v1 = plan.fsm_data.get("scene_version") == "v1"
    scene_getter = get_qqcc_draw_scene_v1 if is_v1 else get_qqcc_draw_scene
    jump_scene = scene_getter(qqcc_config, str(scene.get("jump_draw_scene_id") or ""))
    draw_button_key = "ai_draw_v1" if is_v1 else "ai_draw_v2"
    if jump_scene is None or not is_qqcc_main_button_enabled(
        qqcc_config, draw_button_key
    ):
        return reply_markup
    callback_data = (
        build_quick_draw_v1_scene_callback_data(jump_scene["id"])
        if is_v1
        else build_quick_draw_scene_callback_data(jump_scene["id"])
    )
    jump_row = [
        InlineKeyboardButton(
            f"先去 AI绘图{'V1' if is_v1 else 'V2'}生成「{jump_scene['name']}」",
            callback_data=callback_data,
        )
    ]
    existing_rows = list(reply_markup.inline_keyboard) if reply_markup else []
    return InlineKeyboardMarkup([*existing_rows, jump_row])


async def present_quick_video_entry(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    reply_message: Any,
    plan: QuickVideoEntryPlan,
    reply_text_func: Callable[..., Any],
    interaction_io_func: Callable[..., Any],
    demo_sender_func: Callable[..., Any],
    ref2v_gallery_sender_func: Callable[..., Any],
) -> None:
    scene = plan.scene
    qqcc_config = plan.qqcc_config
    fsm_data = plan.fsm_data
    msg = _t(context, "fsm.quick_video.start", mode_name=plan.mode_name)
    if scene is None or qqcc_config is None:
        await reply_text_func(reply_message, msg, parse_mode="Markdown")
        return

    private_bot_id = get_private_qqcc_bot_id(context)
    demo_kwargs = {"private_bot_id": private_bot_id} if private_bot_id else {}
    await demo_sender_func(
        message=reply_message,
        bot=context.bot,
        scene_kind=(
            "video_v1" if fsm_data.get("scene_version") == "v1" else plan.scene_kind
        ),
        scene=scene,
        **demo_kwargs,
    )

    is_ref2v_scene = bool(
        plan.scene_kind == "ai_video" and str(scene.get("mode") or "") == "ref2v"
    )
    if is_ref2v_scene:
        reference_images = list(scene.get("reference_images") or [])
        reference_names = list(scene.get("reference_image_names") or [])
        if reference_images:
            fsm_data["selected_reference_image"] = reference_images[0]
            fsm_data["selected_reference_name"] = str(
                (reference_names[0] if reference_names else "") or "模板 1"
            )
        gallery_awaitable = ref2v_gallery_sender_func(
            message=reply_message,
            bot=context.bot,
            scene=scene,
        )
        if is_qqcc_bot_context(context):
            await interaction_io_func(
                gallery_awaitable,
                operation="quick_video_ref2v_template_gallery",
                logger=logger,
            )
        else:
            await gallery_awaitable

    scene_cost = resolve_qqcc_scene_display_cost(
        fsm_data=fsm_data,
        qqcc_config=qqcc_config,
    )
    scene_cost_text = (
        _t(context, "fsm.common.estimated_cost", cost=scene_cost)
        if scene_cost is not None
        else None
    )
    if scene_cost_text:
        msg = f"{msg.rstrip()}\n\n{scene_cost_text}"
    copywriting_override = get_qqcc_copywriting_override(
        qqcc_config,
        "ai_video_scene_start"
        if plan.scene_kind == "ai_video"
        else "video_scene_start",
    )
    msg = (
        render_qqcc_copywriting(
            copywriting_override,
            str(scene.get("name") or plan.mode_name),
            cost=scene_cost,
            cost_text=scene_cost_text,
        )
        or msg
    )

    reply_markup = None
    if is_ref2v_scene:
        selected_name = str(fsm_data.get("selected_reference_name") or "模板 1")
        reply_markup = build_ref2v_template_markup(scene)
        msg = build_ref2v_scene_prompt(
            scene=scene,
            selected_name=selected_name,
            cost_text=scene_cost_text,
        )
    reply_markup = _append_draw_jump_button(
        reply_markup=reply_markup,
        scene=scene,
        plan=plan,
    )
    reply_awaitable = reply_text_func(
        reply_message,
        msg,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    if is_qqcc_bot_context(context):
        await interaction_io_func(
            reply_awaitable,
            operation="quick_video_scene_prompt",
            logger=logger,
        )
    else:
        await reply_awaitable
